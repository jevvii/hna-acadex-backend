# Shared utilities for views
import logging
import os
import shutil
import subprocess
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.core.cache import cache
from django.core.files.base import File
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db.utils import OperationalError

from core.models import (
    Activity,
    Enrollment,
    MeetingSession,
    Notification,
    Quiz,
    QuizAttempt,
    Submission,
    User,
)

logger = logging.getLogger(__name__)

# File upload validation constants
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
ALLOWED_DOCUMENT_TYPES = ['application/pdf', 'application/msword',
                          'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Grade computation constants
LETTER_SCALE = [
    (Decimal("97"), "A+"),
    (Decimal("93"), "A"),
    (Decimal("90"), "A-"),
    (Decimal("87"), "B+"),
    (Decimal("83"), "B"),
    (Decimal("80"), "B-"),
    (Decimal("77"), "C+"),
    (Decimal("73"), "C"),
    (Decimal("70"), "C-"),
    (Decimal("60"), "D"),
    (Decimal("0"), "F"),
]

OFFICE_CONVERTIBLE_EXTENSIONS = {"doc", "docx", "ppt", "pptx", "xls", "xlsx"}

GRADE_COMPONENT_WEIGHTS = {
    "activities": Decimal("70"),
    "quizzes": Decimal("20"),
    "attendance": Decimal("10"),
}


def validate_file_upload(file, allowed_types=None):
    """
    Validate uploaded file for type and size.

    Args:
        file: Uploaded file object
        allowed_types: List of allowed MIME types (defaults to images + documents)

    Raises:
        ValidationError: If validation fails
    """
    import magic
    from django.core.exceptions import ValidationError

    if allowed_types is None:
        allowed_types = ALLOWED_IMAGE_TYPES + ALLOWED_DOCUMENT_TYPES

    # Check file size
    if file.size > MAX_FILE_SIZE:
        raise ValidationError(f"File size exceeds maximum of {MAX_FILE_SIZE // (1024*1024)}MB")

    # Check file type using magic (reads actual content, not just extension)
    file.seek(0)
    mime_type = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime_type not in allowed_types:
        raise ValidationError(f"File type '{mime_type}' is not allowed. Allowed types: {', '.join(allowed_types)}")

    return True


def _letter_grade(value: Decimal | None) -> str | None:
    if value is None:
        return None
    for min_score, letter in LETTER_SCALE:
        if value >= min_score:
            return letter
    return "F"


def _quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _compute_activity_percentage(enrollment: Enrollment) -> Decimal | None:
    activities = list(
        Activity.objects.filter(
            course_section=enrollment.course_section,
            is_published=True,
            points__gt=0,
        ).select_related("assignment_group")
    )
    if not activities:
        return None

    # Get all submissions for the student for these activities
    all_submissions = Submission.objects.filter(activity__in=activities, student=enrollment.student)
    submissions_by_activity: dict[str, list[Submission]] = {}
    for s in all_submissions:
        activity_id = str(s.activity_id)
        if activity_id not in submissions_by_activity:
            submissions_by_activity[activity_id] = []
        submissions_by_activity[activity_id].append(s)

    grouped: dict[str, dict[str, Decimal]] = {}
    explicit_weights: dict[str, Decimal] = {}
    explicit_weight_sum = Decimal("0")

    for activity in activities:
        group_key = str(activity.assignment_group_id) if activity.assignment_group_id else "__default__"
        possible = Decimal(activity.points or 0)

        # Get all submissions for this activity
        activity_submissions = submissions_by_activity.get(str(activity.id), [])
        earned = Decimal("0")

        if activity_submissions:
            # Calculate best score based on policy
            scores = [s.score for s in activity_submissions if s.score is not None]
            if scores:
                if activity.score_selection_policy == Activity.ScorePolicy.HIGHEST:
                    earned = max(scores)
                else:  # LATEST
                    # Get the latest submission's score
                    latest = max(activity_submissions, key=lambda s: s.attempt_number)
                    earned = Decimal(latest.score) if latest.score is not None else Decimal("0")

        data = grouped.setdefault(group_key, {"earned": Decimal("0"), "possible": Decimal("0")})
        data["earned"] += earned
        data["possible"] += possible

        if activity.assignment_group and activity.assignment_group.weight_percent is not None:
            weight = Decimal(activity.assignment_group.weight_percent)
            explicit_weights[group_key] = weight

    explicit_weight_sum = sum(explicit_weights.values(), Decimal("0"))
    weighted_enabled = explicit_weight_sum > Decimal("0")

    if weighted_enabled:
        default_weight = max(Decimal("0"), Decimal("100") - explicit_weight_sum)
        raw_weights: dict[str, Decimal] = {}
        for key in grouped.keys():
            raw_weights[key] = explicit_weights.get(key, default_weight if key == "__default__" else Decimal("0"))

        total_weight = sum(raw_weights.values(), Decimal("0"))
        if total_weight <= Decimal("0"):
            weighted_enabled = False
        else:
            normalized = {k: (w * Decimal("100") / total_weight) for k, w in raw_weights.items()}
            weighted_total = Decimal("0")
            for key, data in grouped.items():
                possible = data["possible"]
                if possible <= 0:
                    continue
                group_pct = (data["earned"] / possible) * Decimal("100")
                weighted_total += (group_pct * normalized.get(key, Decimal("0")) / Decimal("100"))
            return _quantize_pct(max(Decimal("0"), min(weighted_total, Decimal("100"))))

    total_possible = sum(d["possible"] for d in grouped.values())
    if total_possible <= 0:
        return None
    total_earned = sum(d["earned"] for d in grouped.values())
    pct = (total_earned / total_possible) * Decimal("100")
    return _quantize_pct(max(Decimal("0"), min(pct, Decimal("100"))))


def _compute_quiz_percentage(enrollment: Enrollment) -> Decimal | None:
    quizzes = list(
        Quiz.objects.filter(course_section=enrollment.course_section, is_published=True).order_by("created_at", "id")
    )
    if not quizzes:
        return None

    quiz_totals_raw = (
        QuizAttempt.objects.filter(quiz__in=quizzes)
        .values("quiz_id")
        .annotate(total=Sum("points"))
    )
    # Import Sum from Django
    from django.db.models import Sum
    quiz_totals_raw = (
        QuizQuestion.objects.filter(quiz__in=quizzes)
        .values("quiz_id")
        .annotate(total=Sum("points"))
    )
    quiz_possible_map = {
        str(row["quiz_id"]): Decimal(str(row["total"] or 0))
        for row in quiz_totals_raw
    }

    # Get all attempts for the student
    attempts = QuizAttempt.objects.filter(
        quiz__in=quizzes,
        student=enrollment.student,
        is_submitted=True,
        score__isnull=False,
    ).order_by("quiz_id", "attempt_number")

    # Group attempts by quiz and calculate score based on policy
    attempts_by_quiz: dict[str, list[QuizAttempt]] = {}
    for attempt in attempts:
        quiz_id = str(attempt.quiz_id)
        if quiz_id not in attempts_by_quiz:
            attempts_by_quiz[quiz_id] = []
        attempts_by_quiz[quiz_id].append(attempt)

    # Build a map of quiz -> selected score based on policy
    score_by_quiz: dict[str, Decimal] = {}
    quiz_policy_map = {str(q.id): q.score_selection_policy for q in quizzes}

    for quiz_id, quiz_attempts in attempts_by_quiz.items():
        scores = [Decimal(str(a.score or 0)) for a in quiz_attempts if a.score is not None]
        if not scores:
            continue
        policy = quiz_policy_map.get(quiz_id, Quiz.ScorePolicy.HIGHEST)
        if policy == Quiz.ScorePolicy.HIGHEST:
            score_by_quiz[quiz_id] = max(scores)
        else:  # LATEST - use the last attempt's score
            score_by_quiz[quiz_id] = scores[-1]

    total_possible = Decimal("0")
    total_earned = Decimal("0")
    for quiz in quizzes:
        possible = quiz_possible_map.get(str(quiz.id), Decimal("0"))
        if possible <= 0:
            continue
        total_possible += possible
        earned = score_by_quiz.get(str(quiz.id), Decimal("0"))
        total_earned += max(Decimal("0"), min(earned, possible))

    if total_possible <= 0:
        return None
    pct = (total_earned / total_possible) * Decimal("100")
    return _quantize_pct(max(Decimal("0"), min(pct, Decimal("100"))))


def _compute_attendance_percentage(enrollment: Enrollment) -> Decimal | None:
    from core.models import AttendanceRecord, MeetingSession

    total_sessions = MeetingSession.objects.filter(course_section=enrollment.course_section).count()
    if total_sessions <= 0:
        return None

    status_counts = {
        row["status"]: row["count"]
        for row in (
            AttendanceRecord.objects.filter(
                meeting__course_section=enrollment.course_section,
                student=enrollment.student,
            )
            .values("status")
            .annotate(count=Count("id"))
        )
    }
    from django.db.models import Count
    present = Decimal(str(status_counts.get(AttendanceRecord.AttendanceStatus.PRESENT, 0)))
    excused = Decimal(str(status_counts.get(AttendanceRecord.AttendanceStatus.EXCUSED, 0)))
    late = Decimal(str(status_counts.get(AttendanceRecord.AttendanceStatus.LATE, 0)))
    attended_units = present + excused + (late * Decimal("0.5"))
    pct = (attended_units / Decimal(str(total_sessions))) * Decimal("100")
    return _quantize_pct(max(Decimal("0"), min(pct, Decimal("100"))))


# Grade computation functions are canonical in common.py
from core.views.common import _compute_enrollment_grade, _recompute_enrollment_grade, _recompute_course_section_grades


def _get_grade_summary_metadata(enrollment: Enrollment) -> dict:
    """
    Compute grade summary metadata for a student's enrollment.
    Returns counts of graded/pending/total items without modifying grade computation.
    """
    from datetime import datetime
    from decimal import Decimal

    course_section = enrollment.course_section
    enrolled_at = enrollment.enrolled_at

    # Get all published activities and quizzes
    activities = Activity.objects.filter(
        course_section=course_section,
        is_published=True,
        points__gt=0,
    ).only('id', 'deadline', 'points')

    quizzes = Quiz.objects.filter(
        course_section=course_section,
        is_published=True,
    ).only('id', 'close_at')

    # Get student's submissions and attempts
    activity_ids = [a.id for a in activities]
    quiz_ids = [q.id for q in quizzes]

    submissions = {
        str(s.activity_id): s
        for s in Submission.objects.filter(
            activity_id__in=activity_ids,
            student=enrollment.student
        )
    }

    attempts = list(QuizAttempt.objects.filter(
        quiz_id__in=quiz_ids,
        student=enrollment.student,
        is_submitted=True,
    ))

    attempts_by_quiz: dict[str, list] = {}
    for a in attempts:
        key = str(a.quiz_id)
        if key not in attempts_by_quiz:
            attempts_by_quiz[key] = []
        attempts_by_quiz[key].append(a)

    graded_items_count = 0
    total_items_count = 0
    pending_count = 0
    excluded_count = 0

    # Process activities
    for activity in activities:
        total_items_count += 1

        # Check if activity deadline is before enrollment (pre-enrollment exclusion)
        if activity.deadline and enrolled_at:
            activity_deadline = activity.deadline
            if isinstance(enrolled_at, str):
                enrolled_at_dt = datetime.fromisoformat(enrolled_at.replace('Z', '+00:00'))
            else:
                enrolled_at_dt = enrolled_at
            if isinstance(activity_deadline, str):
                activity_deadline_dt = datetime.fromisoformat(activity_deadline.replace('Z', '+00:00'))
            else:
                activity_deadline_dt = activity_deadline

            if activity_deadline_dt < enrolled_at_dt:
                excluded_count += 1
                continue

        sub = submissions.get(str(activity.id))
        if sub:
            if sub.score is not None:
                graded_items_count += 1
            elif sub.status in (Submission.SubmissionStatus.SUBMITTED, Submission.SubmissionStatus.LATE):
                pending_count += 1

    # Process quizzes
    for quiz in quizzes:
        # Quizzes don't have pre-enrollment exclusion in the same way
        # but we check close_at similar to activities
        total_items_count += 1

        if quiz.close_at and enrolled_at:
            close_at = quiz.close_at
            if isinstance(enrolled_at, str):
                enrolled_at_dt = datetime.fromisoformat(enrolled_at.replace('Z', '+00:00'))
            else:
                enrolled_at_dt = enrolled_at
            if isinstance(close_at, str):
                close_at_dt = datetime.fromisoformat(close_at.replace('Z', '+00:00'))
            else:
                close_at_dt = close_at

            if close_at_dt < enrolled_at_dt:
                excluded_count += 1
                continue

        quiz_attempts = attempts_by_quiz.get(str(quiz.id), [])
        if quiz_attempts:
            # Check if any attempt has a score
            has_score = any(a.score is not None for a in quiz_attempts)
            if has_score:
                graded_items_count += 1
            else:
                pending_count += 1

    return {
        "graded_items_count": graded_items_count,
        "total_items_count": total_items_count,
        "pending_count": pending_count,
        "excluded_count": excluded_count,
        "has_pending": pending_count > 0,
        "has_grades": graded_items_count > 0,
        "has_items": total_items_count > 0,
    }


def _sync_student_activity_items(student: User):
    from core.models import TodoItem, CalendarEvent

    if student.role != User.Role.STUDENT:
        return

    activities = list(
        Activity.objects.filter(
            is_published=True,
            course_section__enrollments__student=student,
            course_section__enrollments__is_active=True,
        )
        .select_related("course_section")
        .distinct()
    )
    quizzes = list(
        Quiz.objects.filter(
            is_published=True,
            course_section__enrollments__student=student,
            course_section__enrollments__is_active=True,
        )
        .select_related("course_section")
        .distinct()
    )
    activity_ids = [a.id for a in activities]
    quiz_ids = [q.id for q in quizzes]
    submissions = {
        s.activity_id: s
        for s in Submission.objects.filter(student=student, activity_id__in=activity_ids)
    }
    quiz_attempts = (
        QuizAttempt.objects.filter(student=student, quiz_id__in=quiz_ids, is_submitted=True)
        .order_by("quiz_id", "-attempt_number", "-submitted_at")
    )
    latest_attempt_by_quiz: dict[str, QuizAttempt] = {}
    for attempt in quiz_attempts:
        key = str(attempt.quiz_id)
        if key not in latest_attempt_by_quiz:
            latest_attempt_by_quiz[key] = attempt

    for activity in activities:
        sub = submissions.get(activity.id)
        is_done = bool(sub and sub.submitted_at)
        TodoItem.objects.update_or_create(
            user=student,
            activity=activity,
            defaults={
                "title": f"{activity.title}",
                "description": activity.instructions or activity.description or "",
                "due_at": activity.deadline,
                "is_done": is_done,
                "completed_at": sub.submitted_at if is_done else None,
            },
        )
        CalendarEvent.objects.update_or_create(
            creator=student,
            activity=activity,
            defaults={
                "course_section": activity.course_section,
                "title": activity.title,
                "description": activity.instructions or activity.description or "",
                "event_type": CalendarEvent.EventType.DEADLINE,
                "start_at": activity.deadline or timezone.now(),
                "end_at": activity.deadline or None,
                "all_day": activity.deadline is None,
                "is_personal": False,  # Activity-generated events are not user-created
                "color": None,
            },
        )

    for quiz in quizzes:
        attempt = latest_attempt_by_quiz.get(str(quiz.id))
        is_done = bool(attempt and attempt.submitted_at)
        TodoItem.objects.update_or_create(
            user=student,
            quiz=quiz,
            defaults={
                "title": f"{quiz.title}",
                "description": quiz.instructions or "",
                "due_at": quiz.close_at,
                "is_done": is_done,
                "completed_at": attempt.submitted_at if is_done else None,
                "activity": None,
            },
        )

    TodoItem.objects.filter(user=student, activity__isnull=False).exclude(activity_id__in=activity_ids).delete()
    TodoItem.objects.filter(user=student, quiz__isnull=False).exclude(quiz_id__in=quiz_ids).delete()
    CalendarEvent.objects.filter(creator=student, activity__isnull=False).exclude(activity_id__in=activity_ids).delete()


def _sync_course_section_students_activity_items(course_section):
    student_ids = Enrollment.objects.filter(
        course_section=course_section,
        is_active=True,
        student__role=User.Role.STUDENT,
    ).values_list("student_id", flat=True)
    for student in User.objects.filter(id__in=student_ids):
        _sync_student_activity_items(student)


def _sync_student_items_best_effort(student: User, *, min_interval_seconds: int = 12):
    if student.role != User.Role.STUDENT:
        return
    cooldown_key = f"sync-student-items:cooldown:{student.id}"
    lock_key = f"sync-student-items:lock:{student.id}"
    if cache.get(cooldown_key):
        return
    if not cache.add(lock_key, "1", timeout=8):
        return
    try:
        _sync_student_activity_items(student)
        cache.set(cooldown_key, "1", timeout=max(1, int(min_interval_seconds)))
    except OperationalError:
        logger.warning("todo_sync_skipped_db_locked student_id=%s", student.id)
    finally:
        cache.delete(lock_key)


def _build_storage_abs_path(path: str) -> str | None:
    if hasattr(default_storage, "path"):
        try:
            return default_storage.path(path)
        except Exception:
            return None
    return None


def _convert_office_upload_to_pdf_preview(*, request, source_storage_path: str, original_name: str) -> str | None:
    ext = (os.path.splitext(original_name)[1] or "").lower().replace(".", "")
    if ext not in OFFICE_CONVERTIBLE_EXTENSIONS:
        return None

    source_abs = _build_storage_abs_path(source_storage_path)
    if not source_abs or not os.path.exists(source_abs):
        return None

    libreoffice_bin = shutil.which("libreoffice")
    if not libreoffice_bin:
        logger.warning("preview_conversion_skipped_no_libreoffice source=%s", source_storage_path)
        return None

    output_dir = os.path.join(os.path.dirname(source_abs), "__previews__")
    os.makedirs(output_dir, exist_ok=True)

    try:
        subprocess.run(
            [libreoffice_bin, "--headless", "--convert-to", "pdf", "--outdir", output_dir, source_abs],
            check=False,
            timeout=90,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.exception("preview_conversion_failed source=%s", source_storage_path)
        return None

    generated_pdf_abs = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(source_abs))[0]}.pdf")
    if not os.path.exists(generated_pdf_abs):
        logger.warning("preview_conversion_no_output source=%s", source_storage_path)
        return None

    base_name = os.path.splitext(os.path.basename(original_name))[0].replace(" ", "_")
    preview_rel = f"course_files/previews/{request.user.id}/{timezone.now().timestamp()}_{base_name}.pdf"
    try:
        with open(generated_pdf_abs, "rb") as fp:
            saved_preview = default_storage.save(preview_rel, File(fp))
        return request.build_absolute_uri(default_storage.url(saved_preview))
    except Exception:
        logger.exception("preview_storage_failed source=%s", source_storage_path)
        return None


def _notify_students_for_course_section(
    *,
    course_section,
    notif_type: str,
    title: str,
    body: str,
    activity=None,
    quiz=None,
    throttle_seconds: int = 90,
):
    from core.push_notifications import send_push_notification_to_users

    student_ids = list(
        Enrollment.objects.filter(
            course_section=course_section,
            is_active=True,
            student__status=User.Status.ACTIVE,
        )
        .values_list("student_id", flat=True)
        .distinct()
    )
    if not student_ids:
        return

    recent_cutoff = timezone.now() - timedelta(seconds=max(int(throttle_seconds), 0))
    existing_recipient_ids = set(
        Notification.objects.filter(
            recipient_id__in=student_ids,
            type=notif_type,
            title=title,
            course_section=course_section,
            activity=activity,
            quiz=quiz,
            created_at__gte=recent_cutoff,
        ).values_list("recipient_id", flat=True)
    )

    rows = []
    for student_id in student_ids:
        if student_id in existing_recipient_ids:
            continue
        rows.append(
            Notification(
                recipient_id=student_id,
                type=notif_type,
                title=title,
                body=body,
                course_section=course_section,
                activity=activity,
                quiz=quiz,
            )
        )
    if not rows:
        return
    Notification.objects.bulk_create(rows)

    # Send push notifications to students
    # Get student IDs who didn't already receive this notification
    new_recipient_ids = [str(student_id) for student_id in student_ids if student_id not in existing_recipient_ids]

    if new_recipient_ids:
        # Build data payload for deep linking
        data = {
            "type": notif_type,
            "course_section_id": str(course_section.id),
        }
        if activity:
            data["activity_id"] = str(activity.id)
        if quiz:
            data["quiz_id"] = str(quiz.id)

        # Send push notifications asynchronously (in production, use Celery task)
        try:
            send_push_notification_to_users(
                user_ids=new_recipient_ids,
                title=title,
                body=body,
                data=data,
            )
        except Exception as e:
            logger.warning(f"Failed to send push notifications: {e}")