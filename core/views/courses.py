"""
Course management views.
"""
from django.db.models import Count, Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Activity,
    Announcement,
    Course,
    CourseFile,
    CourseSection,
    Enrollment,
    Quiz,
    Submission,
    User,
    WeeklyModule,
)
from core.serializers import (
    ActivitySerializer,
    AnnouncementSerializer,
    CourseFileSerializer,
    QuizSerializer,
    SubmissionSerializer,
    WeeklyModuleSerializer,
)
from core.views.common import (
    _batch_recompute_enrollment_grades,
    _batch_get_grade_summary_metadata,
    _letter_grade,
)
from decimal import Decimal


class StudentCoursesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        enrollments = list(
            Enrollment.objects.filter(student=request.user, is_active=True, course_section__is_active=True)
            .select_related("course_section__course", "course_section__section", "course_section__teacher")
            .order_by("course_section__course__title")
        )

        # Batch compute grades to avoid N+1 queries
        _batch_recompute_enrollment_grades(enrollments)
        grade_summaries = _batch_get_grade_summary_metadata(enrollments)

        data = []
        for e in enrollments:
            cs = e.course_section
            course = cs.course
            sec = cs.section
            course_tag = f"{course.code}@{sec.strand}-{sec.name}" if sec.strand and sec.strand != "NONE" else f"{course.code}@{sec.name}"
            final_grade = float(e.final_grade) if e.final_grade is not None else None

            # Get grade metadata for badge display (from batch-computed results)
            grade_metadata = grade_summaries.get(str(e.id), {})

            data.append(
                {
                    "student_id": str(request.user.id),
                    "course_section_id": str(cs.id),
                    "course_id": str(course.id),
                    "course_code": course.code,
                    "course_title": course.title,
                    "cover_image_url": course.cover_image_url,
                    "color_overlay": course.color_overlay,
                    "section_name": sec.name,
                    "strand": sec.strand,
                    "grade_level": sec.grade_level,
                    "final_grade": final_grade,
                    "final_grade_letter": _letter_grade(Decimal(str(final_grade))) if final_grade is not None else None,
                    "grade_overridden": e.manual_final_grade is not None,
                    "teacher_name": cs.teacher.full_name if cs.teacher else None,
                    "course_tag": course_tag,
                    "semester": cs.semester,
                    "school_year": cs.school_year,
                    # Grade metadata for badge display
                    "grade_summary": grade_metadata,
                }
            )
        return Response(data)


class TeacherCoursesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        course_sections = (
            CourseSection.objects.filter(teacher=request.user, is_active=True)
            .select_related("course", "section")
            .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
            .order_by("course__title")
        )
        data = []
        for cs in course_sections:
            course = cs.course
            sec = cs.section
            course_tag = f"{course.code}@{sec.strand}-{sec.name}" if sec.strand and sec.strand != "NONE" else f"{course.code}@{sec.name}"
            data.append(
                {
                    "teacher_id": str(request.user.id),
                    "course_section_id": str(cs.id),
                    "course_id": str(course.id),
                    "course_code": course.code,
                    "course_title": course.title,
                    "cover_image_url": course.cover_image_url,
                    "color_overlay": course.color_overlay,
                    "section_name": sec.name,
                    "strand": sec.strand,
                    "grade_level": sec.grade_level,
                    "course_tag": course_tag,
                    "student_count": cs.student_count,
                    "semester": cs.semester,
                    "school_year": cs.school_year,
                }
            )
        return Response(data)


class CourseSectionDetailView(APIView):
    """Get a single course section by ID."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        course_section = CourseSection.objects.filter(id=pk).select_related("course", "section", "teacher").first()
        if not course_section:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions
        if request.user.role == User.Role.STUDENT:
            allowed = Enrollment.objects.filter(course_section=course_section, student=request.user, is_active=True).exists()
            if not allowed:
                return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role == User.Role.TEACHER:
            if course_section.teacher_id != request.user.id:
                return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        # Admins can access any course section

        course = course_section.course
        section = course_section.section
        teacher = course_section.teacher

        data = {
            "id": str(course_section.id),
            "course_id": str(course.id),
            "section_id": str(section.id),
            "teacher_id": str(teacher.id) if teacher else None,
            "school_year": course_section.school_year,
            "semester": course_section.semester,
            "is_active": course_section.is_active,
            "course": {
                "id": str(course.id),
                "code": course.code,
                "title": course.title,
                "description": course.description,
                "cover_image_url": course.cover_image_url,
                "color_overlay": course.color_overlay,
                "grade_level": course.grade_level,
                "strand": course.strand,
                "school_year": course.school_year,
                "semester": course.semester,
                "num_weeks": course.num_weeks,
                "is_active": course.is_active,
                "created_at": course.created_at,
                "updated_at": course.updated_at,
            },
            "section": {
                "id": str(section.id),
                "name": section.name,
                "strand": section.strand,
                "grade_level": section.grade_level,
            },
            "teacher": {
                "id": str(teacher.id),
                "first_name": teacher.first_name,
                "last_name": teacher.last_name,
                "full_name": teacher.full_name,
                "email": teacher.email,
                "avatar_url": teacher.avatar_url,
            } if teacher else None,
        }
        return Response(data)


class CourseSectionContentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from django.utils import timezone

        course_section = CourseSection.objects.filter(id=pk).first()
        if not course_section:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.STUDENT:
            allowed = Enrollment.objects.filter(course_section=course_section, student=request.user, is_active=True).exists()
            if not allowed:
                return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if request.user.role == User.Role.TEACHER and course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        modules = WeeklyModule.objects.filter(course_section=course_section).order_by("week_number")
        activities = Activity.objects.filter(course_section=course_section).order_by("deadline")
        files = CourseFile.objects.filter(course_section=course_section).order_by("-created_at")
        if request.user.role == User.Role.STUDENT:
            files = files.filter(is_visible=True)
        announcements = Announcement.objects.filter(course_section=course_section).order_by("-created_at")
        quizzes = Quiz.objects.filter(course_section=course_section).order_by("-created_at")

        activities_data = ActivitySerializer(activities, many=True).data
        quizzes_data = QuizSerializer(quizzes, many=True).data

        if request.user.role == User.Role.STUDENT:
            activity_map = {
                str(s.activity_id): s
                for s in Submission.objects.filter(activity__in=activities, student=request.user)
            }
            activity_stats = (
                Submission.objects.filter(activity__in=activities, score__isnull=False)
                .values("activity_id")
                .annotate(lowest=Count("score"), highest=Count("score"))
            )
            # We need min/max; SQLite compatibility through Python fallback
            submissions_by_activity = {}
            for sub in Submission.objects.filter(activity__in=activities, score__isnull=False):
                key = str(sub.activity_id)
                submissions_by_activity.setdefault(key, []).append(float(sub.score))
            for item in activities_data:
                sub = activity_map.get(item["id"])
                item["my_submission"] = (
                    SubmissionSerializer(sub).data if sub else None
                )
                scores = submissions_by_activity.get(item["id"], [])
                item["class_stats"] = {
                    "lowest_score": min(scores) if scores else None,
                    "highest_score": max(scores) if scores else None,
                    "average_score": (sum(scores) / len(scores)) if scores else None,
                }

            quiz_attempts = (
                QuizAttempt.objects.filter(quiz__in=quizzes, student=request.user, is_submitted=True)
                .order_by("quiz_id", "-attempt_number")
            )
            in_progress_attempts = (
                QuizAttempt.objects.filter(quiz__in=quizzes, student=request.user, is_submitted=False)
                .order_by("quiz_id", "-attempt_number")
            )
            latest_by_quiz = {}
            for attempt in quiz_attempts:
                key = str(attempt.quiz_id)
                if key not in latest_by_quiz:
                    latest_by_quiz[key] = attempt
            in_progress_by_quiz = {}
            for attempt in in_progress_attempts:
                key = str(attempt.quiz_id)
                if key not in in_progress_by_quiz:
                    in_progress_by_quiz[key] = attempt
            for item in quizzes_data:
                quiz_obj = next((q for q in quizzes if str(q.id) == item["id"]), None)
                attempt = latest_by_quiz.get(item["id"])
                in_progress = in_progress_by_quiz.get(item["id"])
                attempts_used = QuizAttempt.objects.filter(quiz_id=item["id"], student=request.user, is_submitted=True).count()
                attempt_limit = quiz_obj.attempt_limit if quiz_obj else 1
                time_remaining = None
                if in_progress and quiz_obj and quiz_obj.time_limit_minutes:
                    elapsed = (timezone.now() - in_progress.started_at).total_seconds()
                    time_remaining = max(int((quiz_obj.time_limit_minutes * 60) - elapsed), 0)
                if attempt:
                    item["my_attempt"] = {
                        "id": str(attempt.id),
                        "score": float(attempt.score) if attempt.score is not None else None,
                        "max_score": float(attempt.max_score) if attempt.max_score is not None else None,
                        "pending_manual_grading": attempt.pending_manual_grading,
                        "is_submitted": attempt.is_submitted,
                        "attempt_number": attempt.attempt_number,
                        "attempts_used": attempts_used,
                        "attempts_remaining": max(attempt_limit - attempts_used, 0),
                        "attempt_limit": attempt_limit,
                    }
                else:
                    item["my_attempt"] = {
                        "id": None,
                        "score": None,
                        "max_score": None,
                        "pending_manual_grading": False,
                        "is_submitted": False,
                        "attempt_number": 0,
                        "attempts_used": attempts_used,
                        "attempts_remaining": max(attempt_limit - attempts_used, 0),
                        "attempt_limit": attempt_limit,
                    }
                item["my_in_progress_attempt"] = (
                    {
                        "attempt_id": str(in_progress.id),
                        "attempt_number": in_progress.attempt_number,
                        "time_remaining_seconds": time_remaining,
                    }
                    if in_progress
                    else None
                )

        return Response(
            {
                "modules": WeeklyModuleSerializer(modules, many=True).data,
                "activities": activities_data,
                "files": CourseFileSerializer(files, many=True).data,
                "announcements": AnnouncementSerializer(announcements, many=True).data,
                "quizzes": quizzes_data,
            }
        )


# Import QuizAttempt for use in CourseSectionContentView
from core.models import QuizAttempt


__all__ = [
    'StudentCoursesView',
    'TeacherCoursesView',
    'CourseSectionDetailView',
    'CourseSectionContentView',
]