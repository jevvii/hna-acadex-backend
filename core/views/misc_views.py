"""
Miscellaneous views including ViewSets for various models.
"""
from django.core.files.storage import default_storage
from django.core.files.base import File
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.db.utils import OperationalError
from django.core.cache import cache
from rest_framework import permissions, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.response import Response
import shutil
import subprocess
import os
import logging

from core.models import (
    Activity,
    Announcement,
    AssignmentGroup,
    CalendarEvent,
    CourseFile,
    CourseSection,
    Enrollment,
    MeetingSession,
    Notification,
    PushToken,
    Quiz,
    QuizAttempt,
    TodoItem,
    User,
    WeeklyModule,
)
from core.permissions import IsAdminRole
from core.serializers import (
    ActivityReminderSerializer,
    ActivitySerializer,
    AnnouncementSerializer,
    AssignmentGroupSerializer,
    CalendarEventSerializer,
    CourseFileSerializer,
    PushTokenSerializer,
    QuizSerializer,
    TodoItemSerializer,
    WeeklyModuleSerializer,
)
from core.views.common import (
    _recompute_course_section_grades,
    _sync_course_section_students_activity_items,
    _sync_student_activity_items,
    _sync_student_items_best_effort,
    _convert_office_upload_to_pdf_preview,
    _notify_students_for_course_section,
    OFFICE_CONVERTIBLE_EXTENSIONS,
)
from core.decorators import rate_limit_file_upload

logger = logging.getLogger(__name__)


class TodoItemViewSet(viewsets.ModelViewSet):
    serializer_class = TodoItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == User.Role.STUDENT:
            _sync_student_items_best_effort(self.request.user)
        return (
            TodoItem.objects.filter(user=self.request.user)
            .select_related("activity__course_section", "quiz__course_section")
            .order_by("is_done", "due_at")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = CalendarEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == User.Role.STUDENT:
            _sync_student_items_best_effort(self.request.user)
        qs = CalendarEvent.objects.filter(Q(creator=self.request.user) | Q(is_personal=False))
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            qs = qs.filter(start_at__gte=start)
        if end:
            qs = qs.filter(start_at__lte=end)
        return qs.order_by("start_at")

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.creator_id != request.user.id and request.user.role != User.Role.ADMIN:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class PushTokenViewSet(viewsets.ModelViewSet):
    """Viewset for managing push notification tokens."""
    serializer_class = PushTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PushToken.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # If token already exists for another user, deactivate it
        token = serializer.validated_data.get('token')
        if token:
            PushToken.objects.filter(token=token).exclude(user=self.request.user).update(is_active=False)
        serializer.save(user=self.request.user)


class ActivityReminderViewSet(viewsets.ModelViewSet):
    """Viewset for managing activity/quiz reminders."""
    serializer_class = ActivityReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from core.models import ActivityReminder
        qs = ActivityReminder.objects.filter(user=self.request.user).select_related('activity', 'quiz')

        # Filter by activity_id or quiz_id if provided
        activity_id = self.request.query_params.get('activity_id')
        quiz_id = self.request.query_params.get('quiz_id')
        reminder_type = self.request.query_params.get('reminder_type')

        if activity_id:
            qs = qs.filter(activity_id=activity_id)
        if quiz_id:
            qs = qs.filter(quiz_id=quiz_id)
        if reminder_type:
            qs = qs.filter(reminder_type=reminder_type)

        return qs.order_by('reminder_datetime')

    def perform_create(self, serializer):
        from core.models import ActivityReminder
        # Validate that the user has access to the activity or quiz
        reminder_type = serializer.validated_data.get('reminder_type')
        activity = serializer.validated_data.get('activity')
        quiz = serializer.validated_data.get('quiz')

        if reminder_type == 'activity' and activity:
            # Check if user is enrolled in the course section
            enrolled = Enrollment.objects.filter(
                course_section=activity.course_section,
                student=self.request.user,
                is_active=True,
            ).exists()
            if not enrolled and self.request.user.role != User.Role.ADMIN:
                raise permissions.PermissionDenied("You are not enrolled in this activity's course section.")

        if reminder_type == 'quiz' and quiz:
            # Check if user is enrolled in the course section
            enrolled = Enrollment.objects.filter(
                course_section=quiz.course_section,
                student=self.request.user,
                is_active=True,
            ).exists()
            if not enrolled and self.request.user.role != User.Role.ADMIN:
                raise permissions.PermissionDenied("You are not enrolled in this quiz's course section.")

        serializer.save(user=self.request.user)


class TeacherCourseSectionScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    course_section_field = "course_section"

    def _get_course_section_id(self):
        payload = getattr(self.request, "data", {}) or {}
        return payload.get("course_section_id") or self.request.query_params.get("course_section_id")

    def _can_access_course_section(self, course_section: CourseSection) -> bool:
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return True
        return user.role == User.Role.TEACHER and course_section.teacher_id == user.id

    def _scope_queryset(self, qs):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.TEACHER:
            lookup = {f"{self.course_section_field}__teacher": user}
            return qs.filter(**lookup)
        return qs.none()

    def get_queryset(self):
        return self._scope_queryset(self.queryset)

    def create(self, request, *args, **kwargs):
        course_section_id = self._get_course_section_id()
        if not course_section_id:
            return Response({"detail": "course_section_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        course_section = CourseSection.objects.filter(id=course_section_id).first()
        if not course_section:
            return Response({"detail": "Course section not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_access_course_section(course_section):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = self.get_object()
        course_section = getattr(instance, self.course_section_field)
        if not self._can_access_course_section(course_section):
            raise permissions.PermissionDenied("Not allowed.")
        serializer.save()

    def perform_destroy(self, instance):
        course_section = getattr(instance, self.course_section_field)
        if not self._can_access_course_section(course_section):
            raise permissions.PermissionDenied("Not allowed.")
        instance.delete()


class WeeklyModuleViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = WeeklyModule.objects.all().order_by("week_number", "sort_order")
    serializer_class = WeeklyModuleSerializer

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Modules are auto-created from the course week count. Edit existing weeks instead."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class AssignmentGroupViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = AssignmentGroup.objects.all().order_by("name")
    serializer_class = AssignmentGroupSerializer

    def perform_create(self, serializer):
        group = serializer.save()
        _recompute_course_section_grades(group.course_section)

    def perform_update(self, serializer):
        group = serializer.save()
        _recompute_course_section_grades(group.course_section)

    def perform_destroy(self, instance):
        course_section = instance.course_section
        super().perform_destroy(instance)
        _recompute_course_section_grades(course_section)


class ActivityViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = Activity.objects.all().order_by("deadline")
    serializer_class = ActivitySerializer

    def get_object(self):
        """Allow students to retrieve activities in their enrolled courses."""
        from django.shortcuts import get_object_or_404
        from rest_framework.exceptions import NotFound

        pk = self.kwargs.get('pk')
        user = self.request.user

        # Get the activity
        activity = Activity.objects.filter(id=pk).first()
        if not activity:
            raise NotFound("Activity not found.")

        # Check permissions based on role
        if user.role == User.Role.ADMIN:
            return activity

        if user.role == User.Role.TEACHER:
            if activity.course_section.teacher_id == user.id:
                return activity
            raise NotFound("Activity not found.")

        if user.role == User.Role.STUDENT:
            # Students can access if enrolled in the course section
            is_enrolled = Enrollment.objects.filter(
                student=user,
                course_section=activity.course_section,
                is_active=True
            ).exists()
            if is_enrolled and activity.is_published:
                return activity
            raise NotFound("Activity not found.")

        raise NotFound("Activity not found.")

    def retrieve(self, request, *args, **kwargs):
        """Allow students to view activities in their enrolled courses."""
        from core.serializers import SubmissionSerializer
        from core.models import Submission

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Add my_submission for students to enable dynamic UI updates after submission
        if request.user.role == User.Role.STUDENT:
            all_submissions = Submission.objects.filter(
                activity=instance,
                student=request.user
            ).order_by('-attempt_number')
            # Latest submission (first in the ordered list)
            latest_submission = all_submissions.first()
            data['my_submission'] = SubmissionSerializer(latest_submission).data if latest_submission else None
            # Include all submissions for attempt history dropdown
            data['my_submissions'] = SubmissionSerializer(all_submissions, many=True).data
            # Include attempt limits
            attempt_limit = instance.attempt_limit or 1
            attempts_used = all_submissions.count()
            data['attempt_limit'] = attempt_limit
            data['attempts_used'] = attempts_used
            data['attempts_remaining'] = max(attempt_limit - attempts_used, 0)

        return Response(data)

    def _validate_weekly_module(self, serializer):
        weekly_module = serializer.validated_data.get("weekly_module")
        course_section = serializer.validated_data.get("course_section") or getattr(serializer.instance, "course_section", None)
        if weekly_module and course_section and weekly_module.course_section_id != course_section.id:
            raise permissions.PermissionDenied("Selected week/topic does not belong to this course section.")
        assignment_group = serializer.validated_data.get("assignment_group")
        if assignment_group and course_section and assignment_group.course_section_id != course_section.id:
            raise permissions.PermissionDenied("Selected assignment group does not belong to this course section.")

    def perform_create(self, serializer):
        self._validate_weekly_module(serializer)
        activity = serializer.save(created_by=self.request.user)
        _recompute_course_section_grades(activity.course_section)
        _sync_course_section_students_activity_items(activity.course_section)
        if activity.is_published:
            _notify_students_for_course_section(
                course_section=activity.course_section,
                notif_type=Notification.NotificationType.NEW_ACTIVITY,
                title=f"New Assignment: {activity.title}",
                body=f"A new assignment was posted in {activity.course_section.course.title}.",
                activity=activity,
            )

    def perform_update(self, serializer):
        self._validate_weekly_module(serializer)
        before = serializer.instance
        old_published = bool(before.is_published)
        old_title = before.title
        old_deadline = before.deadline
        old_points = before.points
        old_instructions = before.instructions
        old_description = before.description

        updated = serializer.save()
        _recompute_course_section_grades(updated.course_section)
        _sync_course_section_students_activity_items(updated.course_section)

        became_published = (not old_published) and bool(updated.is_published)
        changed_while_published = bool(updated.is_published) and (
            updated.title != old_title
            or updated.deadline != old_deadline
            or updated.points != old_points
            or (updated.instructions or "") != (old_instructions or "")
            or (updated.description or "") != (old_description or "")
        )

        if became_published:
            _notify_students_for_course_section(
                course_section=updated.course_section,
                notif_type=Notification.NotificationType.NEW_ACTIVITY,
                title=f"New Assignment: {updated.title}",
                body=f"A new assignment was posted in {updated.course_section.course.title}.",
                activity=updated,
            )
        elif changed_while_published:
            _notify_students_for_course_section(
                course_section=updated.course_section,
                notif_type=Notification.NotificationType.NEW_ACTIVITY,
                title=f"Updated Assignment: {updated.title}",
                body=f"An assignment was updated in {updated.course_section.course.title}.",
                activity=updated,
            )

    def perform_destroy(self, instance):
        course_section = instance.course_section
        super().perform_destroy(instance)
        _recompute_course_section_grades(course_section)
        _sync_course_section_students_activity_items(course_section)


class CourseFileViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = CourseFile.objects.all().order_by("-created_at")
    serializer_class = CourseFileSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _validate_weekly_module(self, serializer):
        weekly_module = serializer.validated_data.get("weekly_module")
        course_section = serializer.validated_data.get("course_section") or getattr(serializer.instance, "course_section", None)
        if weekly_module and course_section and weekly_module.course_section_id != course_section.id:
            raise permissions.PermissionDenied("Selected week/topic does not belong to this course section.")

    def perform_create(self, serializer):
        self._validate_weekly_module(serializer)
        serializer.save(uploader=self.request.user)

    def perform_update(self, serializer):
        self._validate_weekly_module(serializer)
        super().perform_update(serializer)

    def _inject_uploaded_file_data(self, request, payload):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return payload

        path = default_storage.save(
            f"course_files/{request.user.id}/{timezone.now().timestamp()}_{file_obj.name}",
            file_obj,
        )
        file_url = request.build_absolute_uri(default_storage.url(path))
        payload["file_url"] = file_url
        payload["file_name"] = payload.get("file_name") or file_obj.name
        payload["file_size_bytes"] = file_obj.size
        ext = file_obj.name.split(".")[-1].lower() if "." in file_obj.name else None
        payload["file_type"] = payload.get("file_type") or ext
        preview_url = _convert_office_upload_to_pdf_preview(
            request=request,
            source_storage_path=path,
            original_name=file_obj.name,
        )
        if preview_url:
            payload["preview_file_url"] = preview_url
        return payload

    def create(self, request, *args, **kwargs):
        course_section_id = self._get_course_section_id()
        if not course_section_id:
            return Response({"detail": "course_section_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        course_section = CourseSection.objects.filter(id=course_section_id).first()
        if not course_section:
            return Response({"detail": "Course section not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_access_course_section(course_section):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data.copy()
        payload = self._inject_uploaded_file_data(request, payload)
        if not payload.get("file_url"):
            return Response({"detail": "Either file_url or an uploaded file is required."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        payload = request.data.copy()
        payload = self._inject_uploaded_file_data(request, payload)
        if not payload.get("file_url"):
            payload["file_url"] = instance.file_url

        serializer = self.get_serializer(instance, data=payload, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class AnnouncementViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = Announcement.objects.all().order_by("-created_at")
    serializer_class = AnnouncementSerializer

    def perform_create(self, serializer):
        announcement = serializer.save(created_by=self.request.user)

        # Send notifications to students if published
        if announcement.is_published:
            self._send_announcement_notifications(announcement)

    def perform_update(self, serializer):
        announcement = serializer.save()
        # Send notifications if being published for the first time
        if announcement.is_published:
            self._send_announcement_notifications(announcement)

    def _send_announcement_notifications(self, announcement: Announcement):
        """Send in-app notifications and push notifications for announcement."""
        from core.push_notifications import send_push_notification_to_users

        # Determine recipients based on school_wide flag and audience
        if announcement.school_wide:
            # School-wide announcement - notify all teachers and students
            recipient_ids = list(
                User.objects.filter(
                    status=User.Status.ACTIVE,
                    role__in=[User.Role.TEACHER, User.Role.STUDENT],
                ).values_list('id', flat=True)
            )
            course_section_id = None
        else:
            # Course section announcement
            if not announcement.course_section:
                return
            course_section_id = str(announcement.course_section.id)

            # Filter recipients based on audience
            if announcement.audience == Announcement.Audience.TEACHERS_ONLY:
                recipient_ids = [announcement.course_section.teacher_id] if announcement.course_section.teacher else []
            else:
                # ALL - notify all enrolled students
                recipient_ids = list(
                    Enrollment.objects.filter(
                        course_section=announcement.course_section,
                        is_active=True,
                        student__status=User.Status.ACTIVE,
                    ).values_list('student_id', flat=True)
                )

        if not recipient_ids:
            return

        # Create in-app notifications
        notif_type = (
            Notification.NotificationType.SCHOOL_ANNOUNCEMENT
            if announcement.school_wide
            else Notification.NotificationType.COURSE_ANNOUNCEMENT
        )

        notifications = [
            Notification(
                recipient_id=recipient_id,
                type=notif_type,
                title=announcement.title,
                body=announcement.body[:200] if announcement.body else "",
                course_section=announcement.course_section,
                announcement=announcement,
            )
            for recipient_id in recipient_ids
        ]
        Notification.objects.bulk_create(notifications)

        # Send push notifications
        data = {
            "type": notif_type,
            "announcement_id": str(announcement.id),
        }
        if course_section_id:
            data["course_section_id"] = course_section_id

        try:
            send_push_notification_to_users(
                user_ids=[str(uid) for uid in recipient_ids],
                title=announcement.title,
                body=announcement.body[:100] if announcement.body else "",
                data=data,
            )
        except Exception as e:
            logger.warning(f"Failed to send push notifications for announcement: {e}")


class QuizViewSet(TeacherCourseSectionScopedModelViewSet):
    queryset = Quiz.objects.all().order_by("-created_at")
    serializer_class = QuizSerializer

    def get_object(self):
        """Allow students to retrieve quizzes in their enrolled courses."""
        from django.shortcuts import get_object_or_404
        from rest_framework.exceptions import NotFound

        pk = self.kwargs.get('pk')
        user = self.request.user

        # Get the quiz
        quiz = Quiz.objects.filter(id=pk).first()
        if not quiz:
            raise NotFound("Quiz not found.")

        # Check permissions based on role
        if user.role == User.Role.ADMIN:
            return quiz

        if user.role == User.Role.TEACHER:
            if quiz.course_section.teacher_id == user.id:
                return quiz
            raise NotFound("Quiz not found.")

        if user.role == User.Role.STUDENT:
            # Students can access if enrolled in the course section
            is_enrolled = Enrollment.objects.filter(
                student=user,
                course_section=quiz.course_section,
                is_active=True
            ).exists()
            if is_enrolled and quiz.is_published:
                return quiz
            raise NotFound("Quiz not found.")

        raise NotFound("Quiz not found.")

    def retrieve(self, request, *args, **kwargs):
        """Allow students to view quizzes in their enrolled courses."""
        from core.models import QuizAttempt
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Add student attempt information for students
        if request.user.role == User.Role.STUDENT:
            # Get all submitted attempts, ordered by attempt number
            all_attempts = QuizAttempt.objects.filter(
                quiz=instance,
                student=request.user,
                is_submitted=True
            ).order_by("attempt_number")

            # Get latest submitted attempt
            latest_attempt = all_attempts.last() if all_attempts else None

            # Get in-progress attempt
            in_progress = (
                QuizAttempt.objects.filter(
                    quiz=instance,
                    student=request.user,
                    is_submitted=False
                )
                .order_by("-attempt_number")
                .first()
            )

            attempts_used = all_attempts.count()
            attempt_limit = instance.attempt_limit

            # Calculate time remaining for in-progress attempt
            time_remaining = None
            if in_progress and instance.time_limit_minutes:
                elapsed = (timezone.now() - in_progress.started_at).total_seconds()
                time_remaining = max(int((instance.time_limit_minutes * 60) - elapsed), 0)

            if latest_attempt:
                data["my_attempt"] = {
                    "id": str(latest_attempt.id),
                    "score": float(latest_attempt.score) if latest_attempt.score is not None else None,
                    "max_score": float(latest_attempt.max_score) if latest_attempt.max_score is not None else None,
                    "pending_manual_grading": latest_attempt.pending_manual_grading,
                    "is_submitted": latest_attempt.is_submitted,
                    "attempt_number": latest_attempt.attempt_number,
                    "attempts_used": attempts_used,
                    "attempts_remaining": max(attempt_limit - attempts_used, 0),
                    "attempt_limit": attempt_limit,
                }
            else:
                data["my_attempt"] = {
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

            data["my_in_progress_attempt"] = (
                {
                    "attempt_id": str(in_progress.id),
                    "attempt_number": in_progress.attempt_number,
                    "time_remaining_seconds": time_remaining,
                }
                if in_progress
                else None
            )

            # Build attempts array for history display
            attempts_payload = []
            for a in all_attempts:
                attempts_payload.append({
                    "id": str(a.id),
                    "attempt_number": a.attempt_number,
                    "score": float(a.score) if a.score is not None else None,
                    "max_score": float(a.max_score) if a.max_score is not None else None,
                    "pending_manual_grading": a.pending_manual_grading,
                    "is_submitted": a.is_submitted,
                    "submitted_at": a.submitted_at,
                })
            # Add in-progress attempt to the list if exists
            if in_progress:
                attempts_payload.append({
                    "id": str(in_progress.id),
                    "attempt_number": in_progress.attempt_number,
                    "score": None,
                    "max_score": None,
                    "pending_manual_grading": False,
                    "is_submitted": False,
                    "submitted_at": None,
                })
            data["attempts"] = attempts_payload

        return Response(data)

    def _validate_weekly_module(self, serializer):
        weekly_module = serializer.validated_data.get("weekly_module")
        course_section = serializer.validated_data.get("course_section") or getattr(serializer.instance, "course_section", None)
        if weekly_module and course_section and weekly_module.course_section_id != course_section.id:
            raise permissions.PermissionDenied("Selected week/topic does not belong to this course section.")

    def perform_create(self, serializer):
        self._validate_weekly_module(serializer)
        quiz = serializer.save()
        _recompute_course_section_grades(quiz.course_section)
        _sync_course_section_students_activity_items(quiz.course_section)
        if quiz.is_published:
            _notify_students_for_course_section(
                course_section=quiz.course_section,
                notif_type=Notification.NotificationType.NEW_QUIZ,
                title=f"New Quiz: {quiz.title}",
                body=f"A new quiz was posted in {quiz.course_section.course.title}.",
                quiz=quiz,
            )

    def perform_update(self, serializer):
        self._validate_weekly_module(serializer)
        before = serializer.instance
        old_published = bool(before.is_published)
        old_title = before.title
        old_instructions = before.instructions
        old_attempt_limit = before.attempt_limit
        old_time_limit = before.time_limit_minutes
        old_open_at = before.open_at
        old_close_at = before.close_at

        updated = serializer.save()
        _recompute_course_section_grades(updated.course_section)
        _sync_course_section_students_activity_items(updated.course_section)

        became_published = (not old_published) and bool(updated.is_published)
        changed_while_published = bool(updated.is_published) and (
            updated.title != old_title
            or (updated.instructions or "") != (old_instructions or "")
            or updated.attempt_limit != old_attempt_limit
            or updated.time_limit_minutes != old_time_limit
            or updated.open_at != old_open_at
            or updated.close_at != old_close_at
        )

        if became_published:
            _notify_students_for_course_section(
                course_section=updated.course_section,
                notif_type=Notification.NotificationType.NEW_QUIZ,
                title=f"New Quiz: {updated.title}",
                body=f"A new quiz was posted in {updated.course_section.course.title}.",
                quiz=updated,
            )
        elif changed_while_published:
            _notify_students_for_course_section(
                course_section=updated.course_section,
                notif_type=Notification.NotificationType.NEW_QUIZ,
                title=f"Updated Quiz: {updated.title}",
                body=f"A quiz was updated in {updated.course_section.course.title}.",
                quiz=updated,
            )

    def perform_destroy(self, instance):
        course_section = instance.course_section
        super().perform_destroy(instance)
        _recompute_course_section_grades(course_section)
        _sync_course_section_students_activity_items(course_section)


__all__ = [
    'TodoItemViewSet',
    'CalendarEventViewSet',
    'PushTokenViewSet',
    'ActivityReminderViewSet',
    'TeacherCourseSectionScopedModelViewSet',
    'WeeklyModuleViewSet',
    'AssignmentGroupViewSet',
    'ActivityViewSet',
    'CourseFileViewSet',
    'AnnouncementViewSet',
    'QuizViewSet',
]