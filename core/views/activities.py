"""
Activity and submission views.
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import permissions, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Activity,
    ActivityComment,
    Enrollment,
    Notification,
    Submission,
    User,
)
from core.comment_crypto import encrypt_comment_content
from core.permissions import IsAdminRole
from core.serializers import (
    ActivityCommentSerializer,
    ActivitySerializer,
    SubmissionGradeSerializer,
    SubmissionSerializer,
)
from core.grade_computation import recompute_grade_entries_for_student
from core.views.common import (
    _sync_student_activity_items,
    _sync_course_section_students_activity_items,
    _notify_students_for_course_section,
    validate_file_upload,
)
from core.storage import get_storage_url as _get_storage_url
from core.decorators import rate_limit_file_upload

logger = logging.getLogger(__name__)
COMMENT_THREAD_META_PREFIX = "[thread_meta]"
COMMENT_THREAD_META_SUFFIX = "[/thread_meta]"


class ActivitySubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _notify_teacher_submission(self, submission: Submission):
        teacher = submission.activity.course_section.teacher
        if not teacher:
            return

        Notification.objects.create(
            recipient=teacher,
            type=Notification.NotificationType.NEW_ACTIVITY,
            title=f"Submission Received: {submission.activity.title}",
            body=f"{submission.student.full_name} submitted attempt #{submission.attempt_number}.",
            course_section=submission.activity.course_section,
            activity=submission.activity,
        )

    def post(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can submit activities."}, status=status.HTTP_403_FORBIDDEN)

        activity = Activity.objects.filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        enrolled = Enrollment.objects.filter(
            course_section=activity.course_section,
            student=request.user,
            is_active=True,
        ).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not activity.is_published:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check attempt limit
        attempt_limit = activity.attempt_limit or 1
        existing_submissions = Submission.objects.filter(activity=activity, student=request.user).count()
        if existing_submissions >= attempt_limit:
            return Response({"detail": f"Attempt limit reached. You have used {existing_submissions} of {attempt_limit} attempts."}, status=status.HTTP_400_BAD_REQUEST)

        allowed = activity.allowed_file_types or ["all"]
        allowed_set = set([a.lower() for a in allowed if isinstance(a, str)])
        allow_all = "all" in allowed_set
        allow_text = allow_all or "text" in allowed_set
        allow_image = allow_all or "image" in allowed_set
        allow_pdf = allow_all or "pdf" in allowed_set

        text_content = request.data.get("text_content")
        if text_content and not allow_text:
            return Response({"detail": "Text submission is not allowed for this activity."}, status=status.HTTP_400_BAD_REQUEST)

        existing_urls = request.data.get("file_urls") or []
        if not isinstance(existing_urls, list):
            existing_urls = []

        uploaded_urls = []
        files = request.FILES.getlist("files")
        for file_obj in files:
            # Validate file using magic bytes for security
            try:
                validate_file_upload(file_obj)
            except Exception as e:
                return Response({"detail": f"{file_obj.name}: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            ctype = (file_obj.content_type or "").lower()
            is_image = ctype.startswith("image/")
            is_pdf = ctype == "application/pdf" or file_obj.name.lower().endswith(".pdf")
            if (is_image and not allow_image) or (is_pdf and not allow_pdf) or (not is_image and not is_pdf and not allow_all):
                return Response({"detail": f"File type not allowed: {file_obj.name}"}, status=status.HTTP_400_BAD_REQUEST)
            path = default_storage.save(f"submissions/{request.user.id}/{timezone.now().timestamp()}_{file_obj.name}", file_obj)
            uploaded_urls.append(_get_storage_url(path))

        now = timezone.now()
        status_value = Submission.SubmissionStatus.SUBMITTED
        if activity.deadline and now > activity.deadline:
            if not activity.allow_late_submissions:
                return Response({"detail": "Late submissions are not allowed for this activity."}, status=status.HTTP_400_BAD_REQUEST)
            status_value = Submission.SubmissionStatus.LATE

        # Create new submission with incremented attempt_number
        next_attempt_number = existing_submissions + 1
        submission = Submission.objects.create(
            activity=activity,
            student=request.user,
            attempt_number=next_attempt_number,
            file_urls=existing_urls + uploaded_urls,
            text_content=text_content,
            submitted_at=now,
            status=status_value,
        )
        _sync_student_activity_items(request.user)
        self._notify_teacher_submission(submission)
        return Response(SubmissionSerializer(submission).data)


class ActivityMySubmissionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can view own submission here."}, status=status.HTTP_403_FORBIDDEN)
        activity = Activity.objects.select_related("course_section").filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)
        enrolled = Enrollment.objects.filter(
            course_section=activity.course_section,
            student=request.user,
            is_active=True,
        ).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not activity.is_published:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)
        # Return the latest submission
        submission = Submission.objects.filter(activity_id=pk, student=request.user).order_by("-attempt_number").first()
        # Also return all submissions for the student's reference
        all_submissions = Submission.objects.filter(activity_id=pk, student=request.user).order_by("-attempt_number")
        attempt_limit = activity.attempt_limit if activity else 1
        attempts_used = all_submissions.count()
        return Response({
            "submission": SubmissionSerializer(submission).data if submission else None,
            "all_submissions": SubmissionSerializer(all_submissions, many=True).data,
            "attempt_limit": attempt_limit,
            "attempts_used": attempts_used,
            "attempts_remaining": max(attempt_limit - attempts_used, 0),
        })


class ActivitySubmissionsForTeacherView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        activity = Activity.objects.select_related("course_section").filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.TEACHER and activity.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Get all submissions ordered by attempt number
        all_submissions = Submission.objects.filter(activity=activity).select_related("student").order_by("student_id", "-attempt_number")

        # Group submissions by student
        submissions_by_student: dict[str, list[Submission]] = {}
        for s in all_submissions:
            student_id = str(s.student_id)
            if student_id not in submissions_by_student:
                submissions_by_student[student_id] = []
            submissions_by_student[student_id].append(s)

        # Get latest submission per student (first in the list due to ordering)
        latest_by_student = {student_id: submissions[0] for student_id, submissions in submissions_by_student.items()}

        enrolled_students = User.objects.filter(
            enrollments__course_section=activity.course_section,
            enrollments__is_active=True,
            role=User.Role.STUDENT,
        ).distinct().order_by("last_name", "first_name")

        payload = []
        for student in enrolled_students:
            student_id = str(student.id)
            all_student_subs = submissions_by_student.get(student_id, [])
            latest_sub = latest_by_student.get(student_id)

            # Calculate best score based on policy
            best_score = None
            if all_student_subs:
                scores = [s.score for s in all_student_subs if s.score is not None]
                if scores:
                    if activity.score_selection_policy == Activity.ScorePolicy.HIGHEST:
                        best_score = max(scores)
                    else:
                        best_score = scores[-1]  # Latest score

            # Base submission data
            row = SubmissionSerializer(latest_sub).data if latest_sub else {
                "id": None,
                "activity_id": str(activity.id),
                "student_id": str(student.id),
                "attempt_number": None,
                "file_urls": [],
                "text_content": None,
                "status": Submission.SubmissionStatus.NOT_SUBMITTED,
                "score": None,
                "feedback": None,
                "submitted_at": None,
                "graded_at": None,
                "created_at": None,
                "updated_at": None,
            }
            row["enrollment_status"] = "enrolled"
            row["student_name"] = student.full_name
            row["student_email"] = student.email
            row["attempt_limit"] = activity.attempt_limit
            row["attempts_used"] = len(all_student_subs)
            row["attempts_remaining"] = max(activity.attempt_limit - len(all_student_subs), 0)
            row["all_submissions"] = SubmissionSerializer(all_student_subs, many=True).data
            row["best_score"] = best_score
            row["score_selection_policy"] = activity.score_selection_policy
            payload.append(row)
        return Response(payload)


class ActivitySubmissionGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        from core.models import AuditLog

        submission = Submission.objects.select_related("activity__course_section").filter(id=pk).first()
        if not submission:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.TEACHER and submission.activity.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Check if this is a new grade being set
        was_ungraded = submission.score is None

        serializer = SubmissionGradeSerializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        graded = serializer.save(graded_at=timezone.now())
        if graded.score is not None:
            graded.status = Submission.SubmissionStatus.GRADED
            graded.save(update_fields=["status", "updated_at"])
            recompute_grade_entries_for_student(graded.activity.course_section, graded.student)

            # Audit log the grade change
            AuditLog.log(
                request,
                action='grade_change',
                target_type='Submission',
                target_id=None,  # Can't store UUID in IntegerField
                details={
                    'submission_id': str(graded.id),
                    'student_id': str(graded.student.id),
                    'student_email': graded.student.email,
                    'activity_id': str(graded.activity.id),
                    'activity_title': graded.activity.title,
                    'score': float(graded.score) if graded.score else None,
                    'feedback': graded.feedback,
                }
            )

            # Send push notification to student when grade is released
            if was_ungraded:
                self._send_grade_notification(graded)

        return Response(SubmissionSerializer(graded).data)

    def _send_grade_notification(self, submission: Submission):
        """Send push notification to student when grade is released."""
        from core.push_notifications import send_push_notification_to_users

        try:
            activity = submission.activity
            student = submission.student

            # Create in-app notification
            Notification.objects.create(
                recipient=student,
                type=Notification.NotificationType.GRADE_RELEASED,
                title=f"Grade Released: {activity.title}",
                body=f"Your submission for '{activity.title}' has been graded. Score: {submission.score}/{activity.points}",
                course_section=activity.course_section,
                activity=activity,
            )

            # Send push notification
            data = {
                "type": "grade_released",
                "activity_id": str(activity.id),
                "course_section_id": str(activity.course_section_id),
            }

            send_push_notification_to_users(
                user_ids=[str(student.id)],
                title=f"Grade Released: {activity.title}",
                body=f"Your submission has been graded. Score: {submission.score}/{activity.points}",
                data=data,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to send grade notification: {e}")


class ActivityStudentGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        from core.models import AuditLog

        activity = Activity.objects.select_related("course_section").filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.TEACHER and activity.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        student_id = request.data.get("student_id")
        if not student_id:
            return Response({"detail": "student_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        student = User.objects.filter(id=student_id, role=User.Role.STUDENT).first()
        if not student:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        enrolled = Enrollment.objects.filter(
            course_section=activity.course_section,
            student=student,
            is_active=True,
        ).exists()
        if not enrolled:
            return Response(
                {"detail": "Student is not actively enrolled in this course section."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        score_raw = request.data.get("score")
        if score_raw in [None, ""]:
            return Response({"detail": "score is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            score_value = Decimal(str(score_raw))
        except (TypeError, ValueError, InvalidOperation):
            return Response({"detail": "score must be a valid number."}, status=status.HTTP_400_BAD_REQUEST)

        if score_value < 0:
            return Response({"detail": "score cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)

        max_points = Decimal(str(activity.points or 0))
        if score_value > max_points:
            return Response(
                {"detail": f"score cannot exceed activity points ({activity.points})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        feedback_raw = request.data.get("feedback")
        feedback_value = feedback_raw if isinstance(feedback_raw, str) and feedback_raw.strip() else None

        latest_submission = (
            Submission.objects.filter(activity=activity, student=student)
            .order_by("-attempt_number")
            .first()
        )
        was_ungraded = latest_submission.score is None if latest_submission else True

        now = timezone.now()

        if latest_submission:
            serializer = SubmissionGradeSerializer(
                latest_submission,
                data={"score": score_value, "feedback": feedback_value},
                partial=True,
            )
            serializer.is_valid(raise_exception=True)
            graded = serializer.save(graded_at=now)
            graded.status = Submission.SubmissionStatus.GRADED
            update_fields = ["status", "updated_at"]
            if graded.submitted_at is None:
                graded.submitted_at = now
                update_fields.append("submitted_at")
            graded.save(update_fields=update_fields)
        else:
            graded = Submission.objects.create(
                activity=activity,
                student=student,
                attempt_number=1,
                file_urls=[],
                text_content=None,
                status=Submission.SubmissionStatus.GRADED,
                score=score_value,
                feedback=feedback_value,
                submitted_at=now,
                graded_at=now,
            )

        AuditLog.log(
            request,
            action='grade_change',
            target_type='Submission',
            target_id=None,  # Can't store UUID in IntegerField
            details={
                'submission_id': str(graded.id),
                'student_id': str(graded.student.id),
                'student_email': graded.student.email,
                'activity_id': str(graded.activity.id),
                'activity_title': graded.activity.title,
                'score': float(graded.score) if graded.score is not None else None,
                'feedback': graded.feedback,
            }
        )

        if was_ungraded:
            self._send_grade_notification(graded)

        recompute_grade_entries_for_student(activity.course_section, student)

        return Response(SubmissionSerializer(graded).data)

    def _send_grade_notification(self, submission: Submission):
        """Send push notification to student when grade is released."""
        from core.push_notifications import send_push_notification_to_users

        try:
            activity = submission.activity
            student = submission.student

            Notification.objects.create(
                recipient=student,
                type=Notification.NotificationType.GRADE_RELEASED,
                title=f"Grade Released: {activity.title}",
                body=f"Your submission for '{activity.title}' has been graded. Score: {submission.score}/{activity.points}",
                course_section=activity.course_section,
                activity=activity,
            )

            data = {
                "type": "grade_released",
                "activity_id": str(activity.id),
                "course_section_id": str(activity.course_section_id),
            }

            send_push_notification_to_users(
                user_ids=[str(student.id)],
                title=f"Grade Released: {activity.title}",
                body=f"Your submission has been graded. Score: {submission.score}/{activity.points}",
                data=data,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to send grade notification: {e}")


class ActivityCommentViewSet(viewsets.ModelViewSet):
    """ViewSet for activity comments - allows students and teachers to comment on activities."""

    queryset = ActivityComment.objects.all().select_related(
        "author",
        "activity",
        "activity__course_section",
        "submission",
        "submission__student",
        "thread_student",
    ).prefetch_related("replies__author", "replies__thread_student")
    serializer_class = ActivityCommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        """Role-scoped access with optional activity/submission filters."""
        qs = super().get_queryset()
        user = self.request.user

        if user.role == User.Role.STUDENT:
            qs = qs.filter(
                Q(author=user) | Q(submission__student=user) | Q(thread_student=user),
                activity__course_section__enrollments__student=user,
                activity__course_section__enrollments__is_active=True,
            ).distinct()
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(activity__course_section__teacher=user)
        elif user.role != User.Role.ADMIN:
            return qs.none()

        activity_id = self.request.query_params.get('activity_id')
        submission_id = self.request.query_params.get('submission_id')

        if activity_id:
            qs = qs.filter(activity_id=activity_id)
        if submission_id:
            qs = qs.filter(submission_id=submission_id)

        # Only return top-level comments (parent=None), replies are nested
        qs = qs.filter(parent=None)

        return qs.order_by('created_at')

    def _parse_file_urls(self, request):
        raw = request.data.get("file_urls")
        if hasattr(request.data, "getlist"):
            values = [v for v in request.data.getlist("file_urls") if v not in (None, "")]
            if len(values) > 1:
                raw = values
            elif len(values) == 1 and values[0] and values[0] != raw:
                raw = values[0]

        if raw in (None, "", []):
            return []
        if isinstance(raw, list):
            return [str(item) for item in raw if item]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if item]
            except json.JSONDecodeError:
                return [raw]
        return []

    def _encode_thread_notification_body(self, message: str, thread_student_id):
        meta = json.dumps(
            {
                "kind": "activity_comment",
                "thread_student_id": str(thread_student_id),
            },
            separators=(",", ":"),
        )
        return f"{message}\n\n{COMMENT_THREAD_META_PREFIX}{meta}{COMMENT_THREAD_META_SUFFIX}"

    def _notify_thread_participant(self, comment: ActivityComment):
        activity = comment.activity
        course_section = activity.course_section
        if not course_section:
            return

        teacher = course_section.teacher
        thread_student = comment.thread_student or (comment.submission.student if comment.submission_id else None)
        if not thread_student:
            return

        recipient = None
        body = None

        if comment.author.role == User.Role.STUDENT:
            recipient = teacher
            if recipient:
                body = self._encode_thread_notification_body(
                    f"{comment.author.full_name} commented on the private activity thread.",
                    thread_student.id,
                )
        elif comment.author.role == User.Role.TEACHER:
            recipient = thread_student
            body = self._encode_thread_notification_body(
                f"{comment.author.full_name} replied on your private activity thread.",
                thread_student.id,
            )

        if not recipient or recipient.id == comment.author_id or not body:
            return

        Notification.objects.create(
            recipient=recipient,
            type=Notification.NotificationType.SYSTEM,
            title=f"New comment on {activity.title}",
            body=body,
            course_section=course_section,
            activity=activity,
        )

    def create(self, request, *args, **kwargs):
        """Create a new comment with optional file attachments."""
        activity_id = request.data.get('activity_id')
        if not activity_id:
            return Response({"detail": "activity_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        activity = Activity.objects.select_related("course_section").filter(id=activity_id).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        submission_id = request.data.get("submission_id")
        student_id = request.data.get("student_id")
        submission = None
        if submission_id:
            submission = Submission.objects.select_related("student").filter(
                id=submission_id,
                activity=activity,
            ).first()
            if not submission:
                return Response({"detail": "Submission not found for this activity."}, status=status.HTTP_404_NOT_FOUND)

        # Check user access and enforce one-to-one conversation scope.
        if request.user.role == User.Role.STUDENT:
            if not activity.is_published:
                return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)
            enrolled = Enrollment.objects.filter(
                course_section=activity.course_section,
                student=request.user,
                is_active=True,
            ).exists()
            if not enrolled:
                return Response({"detail": "You are not enrolled in this activity's course section."}, status=status.HTTP_403_FORBIDDEN)
            if submission and submission.student_id != request.user.id:
                return Response({"detail": "You can only comment on your own submission."}, status=status.HTTP_403_FORBIDDEN)
            if student_id and str(student_id) != str(request.user.id):
                return Response({"detail": "student_id must match your own account."}, status=status.HTTP_400_BAD_REQUEST)
        elif request.user.role == User.Role.TEACHER:
            if activity.course_section.teacher_id != request.user.id:
                return Response({"detail": "You are not the teacher of this course section."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role != User.Role.ADMIN:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        # Handle file uploads
        file_urls = self._parse_file_urls(request)

        # Process uploaded files
        files = request.FILES.getlist('files')
        for file_obj in files:
            path = default_storage.save(
                f"comments/{request.user.id}/{timezone.now().timestamp()}_{file_obj.name}",
                file_obj,
            )
            file_urls.append(_get_storage_url(path))

        content = request.data.get('content')
        parent_id = request.data.get('parent_id')
        if isinstance(content, str):
            content = content.strip()

        if not content and not file_urls:
            return Response({"detail": "Comment content or attachment is required."}, status=status.HTTP_400_BAD_REQUEST)

        parent_comment = None
        if parent_id:
            parent_comment = ActivityComment.objects.select_related("submission", "thread_student", "author").filter(id=parent_id).first()
            if not parent_comment:
                return Response({"detail": "Parent comment not found."}, status=status.HTTP_404_NOT_FOUND)
            # Parent must be for the same activity
            if str(parent_comment.activity_id) != str(activity_id):
                return Response({"detail": "Parent comment must be for the same activity."}, status=status.HTTP_400_BAD_REQUEST)
            parent_submission_id = str(parent_comment.submission_id) if parent_comment.submission_id else None
            current_submission_id = str(submission.id) if submission else None
            if parent_submission_id != current_submission_id:
                return Response({"detail": "Parent comment must belong to the same submission thread."}, status=status.HTTP_400_BAD_REQUEST)

        thread_student = submission.student if submission else None
        if request.user.role == User.Role.STUDENT:
            thread_student = submission.student if submission else request.user
        elif request.user.role == User.Role.TEACHER:
            if not thread_student and parent_comment:
                thread_student = (
                    parent_comment.thread_student
                    or (parent_comment.submission.student if parent_comment.submission_id else None)
                    or (parent_comment.author if parent_comment.author.role == User.Role.STUDENT else None)
                )
            if not thread_student and student_id:
                thread_student = User.objects.filter(
                    id=student_id,
                    role=User.Role.STUDENT,
                    enrollments__course_section=activity.course_section,
                    enrollments__is_active=True,
                ).first()
                if not thread_student:
                    return Response(
                        {"detail": "student_id must belong to an active student in this course section."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if not thread_student:
                return Response(
                    {"detail": "student_id is required when submission_id is not provided for teacher comments."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if student_id and str(thread_student.id) != str(student_id):
                return Response(
                    {"detail": "student_id does not match the target thread."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif request.user.role == User.Role.ADMIN and not thread_student and student_id:
            thread_student = User.objects.filter(id=student_id, role=User.Role.STUDENT).first()

        if parent_comment:
            parent_thread_student = (
                parent_comment.thread_student
                or (parent_comment.submission.student if parent_comment.submission_id else None)
                or (parent_comment.author if parent_comment.author.role == User.Role.STUDENT else None)
            )
            if parent_thread_student and thread_student and parent_thread_student.id != thread_student.id:
                return Response({"detail": "Parent comment must belong to the same student thread."}, status=status.HTTP_400_BAD_REQUEST)
            if parent_thread_student and not thread_student:
                thread_student = parent_thread_student

        comment = ActivityComment.objects.create(
            activity=activity,
            submission=submission,
            thread_student=thread_student,
            author=request.user,
            parent=parent_comment,
            content=encrypt_comment_content(content),
            file_urls=file_urls if file_urls else None,
        )

        try:
            self._notify_thread_participant(comment)
        except Exception as exc:
            logger.warning("Failed to send activity comment notification: %s", exc)

        serializer = self.get_serializer(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update a comment - only the author can update."""
        comment = self.get_object()
        if comment.author != request.user:
            return Response({"detail": "You can only edit your own comments."}, status=status.HTTP_403_FORBIDDEN)
        partial = kwargs.pop("partial", False)
        data = request.data.copy()
        if "content" in data:
            content = data.get("content")
            if isinstance(content, str):
                content = content.strip()
            data["content"] = encrypt_comment_content(content)
        serializer = self.get_serializer(comment, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(comment).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a comment - only the author can delete."""
        comment = self.get_object()
        if comment.author != request.user:
            return Response({"detail": "You can only delete your own comments."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class ActivityCommentsByActivityView(APIView):
    """Get comments for a specific activity with per-user privacy."""

    permission_classes = [permissions.IsAuthenticated]

    def _is_unscoped_visible(self, comment, thread_student_id=None):
        if comment.submission_id is not None:
            return False
        if not thread_student_id:
            return comment.thread_student_id is None
        normalized_thread_student_id = str(thread_student_id)
        return (
            str(comment.thread_student_id) == normalized_thread_student_id
            or (comment.thread_student_id is None and str(comment.author_id) == normalized_thread_student_id)
        )

    def _attach_visible_replies(self, comments, submission_ids, participant_ids, include_unscoped=False, thread_student_id=None):
        normalized_submission_ids = {str(sid) for sid in submission_ids}
        normalized_participants = {str(pid) for pid in participant_ids if pid}
        filtered = []
        for comment in comments:
            visible_replies = [
                reply for reply in comment.replies.all()
                if str(reply.author_id) in normalized_participants
                and (
                    (include_unscoped and self._is_unscoped_visible(reply, thread_student_id=thread_student_id))
                    or (str(reply.submission_id) in normalized_submission_ids)
                )
            ]
            comment._visible_replies = visible_replies
            filtered.append(comment)
        return filtered

    def _query_thread(self, activity, submission_ids, participant_ids, include_unscoped=False, thread_student_id=None):
        comments_qs = ActivityComment.objects.filter(
            activity=activity,
            parent=None,
            author_id__in=participant_ids,
        )
        if include_unscoped:
            unscoped_filter = (
                Q(submission__isnull=True, thread_student_id=thread_student_id)
                | Q(submission__isnull=True, thread_student__isnull=True, author_id=thread_student_id)
            )
            comments_qs = comments_qs.filter(Q(submission_id__in=submission_ids) | unscoped_filter)
        else:
            comments_qs = comments_qs.filter(submission_id__in=submission_ids)

        comments = comments_qs.select_related("author").prefetch_related("replies__author", "replies__thread_student").order_by("created_at")
        return self._attach_visible_replies(
            comments,
            submission_ids,
            participant_ids,
            include_unscoped=include_unscoped,
            thread_student_id=thread_student_id,
        )

    def get(self, request, pk):
        """Get one-to-one comments for a specific activity thread."""
        activity = Activity.objects.select_related("course_section").filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        teacher_id = activity.course_section.teacher_id if activity.course_section else None
        submission_id = request.query_params.get("submission_id")
        student_id = request.query_params.get("student_id")

        if request.user.role == User.Role.STUDENT:
            if not activity.is_published:
                return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)
            enrolled = Enrollment.objects.filter(
                course_section=activity.course_section,
                student=request.user,
                is_active=True,
            ).exists()
            if not enrolled:
                return Response({"detail": "You are not enrolled in this activity's course section."}, status=status.HTTP_403_FORBIDDEN)

            if submission_id:
                student_submission = Submission.objects.filter(
                    id=submission_id,
                    activity=activity,
                    student=request.user,
                ).first()
                if not student_submission:
                    return Response([])
                comments = self._query_thread(
                    activity=activity,
                    submission_ids=[student_submission.id],
                    participant_ids=[request.user.id, teacher_id],
                    include_unscoped=False,
                    thread_student_id=request.user.id,
                )
            else:
                student_submission_ids = list(
                    Submission.objects.filter(
                        activity=activity,
                        student=request.user,
                    ).values_list("id", flat=True)
                )
                comments = self._query_thread(
                    activity=activity,
                    submission_ids=student_submission_ids,
                    participant_ids=[request.user.id, teacher_id],
                    include_unscoped=True,
                    thread_student_id=request.user.id,
                )
            serializer = ActivityCommentSerializer(comments, many=True, context={"request": request})
            return Response(serializer.data)

        if request.user.role == User.Role.TEACHER:
            if activity.course_section.teacher_id != request.user.id:
                return Response({"detail": "You are not the teacher of this course section."}, status=status.HTTP_403_FORBIDDEN)

            if submission_id:
                target_submission = Submission.objects.filter(
                    id=submission_id,
                    activity=activity,
                ).first()
                if not target_submission:
                    return Response({"detail": "Submission not found for this activity."}, status=status.HTTP_404_NOT_FOUND)
                comments = self._query_thread(
                    activity=activity,
                    submission_ids=[target_submission.id],
                    participant_ids=[request.user.id, target_submission.student_id],
                    include_unscoped=True,
                    thread_student_id=target_submission.student_id,
                )
                serializer = ActivityCommentSerializer(comments, many=True, context={"request": request})
                return Response(serializer.data)

            if student_id:
                target_student = User.objects.filter(
                    id=student_id,
                    role=User.Role.STUDENT,
                    enrollments__course_section=activity.course_section,
                    enrollments__is_active=True,
                ).first()
                if not target_student:
                    return Response([])
                student_submission_ids = list(
                    Submission.objects.filter(
                        activity=activity,
                        student_id=target_student.id,
                    ).values_list("id", flat=True)
                )
                comments = self._query_thread(
                    activity=activity,
                    submission_ids=student_submission_ids,
                    participant_ids=[request.user.id, target_student.id],
                    include_unscoped=True,
                    thread_student_id=target_student.id,
                )
                serializer = ActivityCommentSerializer(comments, many=True, context={"request": request})
                return Response(serializer.data)

            return Response(
                {"detail": "submission_id or student_id is required for teacher comment threads."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.role == User.Role.ADMIN:
            comments = ActivityComment.objects.filter(
                activity=activity,
                parent=None,
            ).select_related("author").prefetch_related("replies__author").order_by("created_at")
            serializer = ActivityCommentSerializer(comments, many=True, context={"request": request})
            return Response(serializer.data)

        return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)


__all__ = [
    'ActivitySubmitView',
    'ActivityMySubmissionView',
    'ActivitySubmissionsForTeacherView',
    'ActivitySubmissionGradeView',
    'ActivityStudentGradeView',
    'ActivityCommentViewSet',
    'ActivityCommentsByActivityView',
]
