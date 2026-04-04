"""
Activity and submission views.
"""
from django.core.files.storage import default_storage
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
from core.permissions import IsAdminRole
from core.serializers import (
    ActivityCommentSerializer,
    ActivitySerializer,
    SubmissionGradeSerializer,
    SubmissionSerializer,
)
from core.views.common import (
    _recompute_enrollment_grade,
    _sync_student_activity_items,
    _sync_course_section_students_activity_items,
    _notify_students_for_course_section,
    validate_file_upload,
)
from core.decorators import rate_limit_file_upload


class ActivitySubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

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
            uploaded_urls.append(default_storage.url(path))

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
        enrollment = Enrollment.objects.filter(course_section=activity.course_section, student=request.user, is_active=True).first()
        if enrollment:
            _recompute_enrollment_grade(enrollment)
        _sync_student_activity_items(request.user)
        return Response(SubmissionSerializer(submission).data)


class ActivityMySubmissionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can view own submission here."}, status=status.HTTP_403_FORBIDDEN)
        # Return the latest submission
        submission = Submission.objects.filter(activity_id=pk, student=request.user).order_by("-attempt_number").first()
        # Also return all submissions for the student's reference
        all_submissions = Submission.objects.filter(activity_id=pk, student=request.user).order_by("-attempt_number")
        activity = Activity.objects.filter(id=pk).first()
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

            # Audit log the grade change
            AuditLog.log(
                request,
                action='grade_change',
                target_type='Submission',
                target_id=graded.id,
                details={
                    'student_id': str(graded.student.id),
                    'student_email': graded.student.email,
                    'activity_id': str(graded.activity.id),
                    'activity_title': graded.activity.title,
                    'score': float(graded.score) if graded.score else None,
                    'feedback': graded.feedback,
                }
            )

            enrollment = Enrollment.objects.filter(
                course_section=graded.activity.course_section,
                student=graded.student,
                is_active=True,
            ).first()
            if enrollment:
                _recompute_enrollment_grade(enrollment)

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


class ActivityCommentViewSet(viewsets.ModelViewSet):
    """ViewSet for activity comments - allows students and teachers to comment on activities."""

    queryset = ActivityComment.objects.all().select_related('author', 'activity').prefetch_related('replies')
    serializer_class = ActivityCommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        """Filter comments by activity_id, optionally filter by submission_id."""
        qs = super().get_queryset()

        activity_id = self.request.query_params.get('activity_id')
        submission_id = self.request.query_params.get('submission_id')

        if activity_id:
            qs = qs.filter(activity_id=activity_id)
        if submission_id:
            qs = qs.filter(submission_id=submission_id)

        # Only return top-level comments (parent=None), replies are nested
        qs = qs.filter(parent=None)

        return qs.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Create a new comment with optional file attachments."""
        activity_id = request.data.get('activity_id')
        if not activity_id:
            return Response({"detail": "activity_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        activity = Activity.objects.filter(id=activity_id).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check user access - student must be enrolled, teacher must teach the course
        if request.user.role == User.Role.STUDENT:
            enrolled = Enrollment.objects.filter(
                course_section=activity.course_section,
                student=request.user,
                is_active=True,
            ).exists()
            if not enrolled:
                return Response({"detail": "You are not enrolled in this activity's course section."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role == User.Role.TEACHER:
            teaches = CourseSection.objects.filter(
                id=activity.course_section_id,
                teacher=request.user,
            ).exists()
            if not teaches:
                return Response({"detail": "You are not the teacher of this course section."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role != User.Role.ADMIN:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        # Handle file uploads
        file_urls = request.data.get('file_urls') or []
        if not isinstance(file_urls, list):
            file_urls = []

        # Process uploaded files
        files = request.FILES.getlist('files')
        for file_obj in files:
            path = default_storage.save(
                f"comments/{request.user.id}/{timezone.now().timestamp()}_{file_obj.name}",
                file_obj,
            )
            file_urls.append(request.build_absolute_uri(default_storage.url(path)))

        content = request.data.get('content')
        parent_id = request.data.get('parent_id')
        submission_id = request.data.get('submission_id')

        parent_comment = None
        if parent_id:
            parent_comment = ActivityComment.objects.filter(id=parent_id).first()
            if not parent_comment:
                return Response({"detail": "Parent comment not found."}, status=status.HTTP_404_NOT_FOUND)
            # Parent must be for the same activity
            if str(parent_comment.activity_id) != str(activity_id):
                return Response({"detail": "Parent comment must be for the same activity."}, status=status.HTTP_400_BAD_REQUEST)

        comment = ActivityComment.objects.create(
            activity=activity,
            submission_id=submission_id,
            author=request.user,
            parent=parent_comment,
            content=content,
            file_urls=file_urls if file_urls else None,
        )

        serializer = self.get_serializer(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update a comment - only the author can update."""
        comment = self.get_object()
        if comment.author != request.user:
            return Response({"detail": "You can only edit your own comments."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete a comment - only the author can delete."""
        comment = self.get_object()
        if comment.author != request.user:
            return Response({"detail": "You can only delete your own comments."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class ActivityCommentsByActivityView(APIView):
    """Get comments for a specific activity with per-user privacy."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Get comments for an activity based on user role and involvement."""
        from django.db.models import Q
        from core.models import CourseSection

        activity = Activity.objects.filter(id=pk).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get the course section teacher for this activity
        course_section = activity.course_section
        teacher_id = course_section.teacher_id if course_section else None

        if request.user.role == User.Role.STUDENT:
            # Check enrollment
            enrolled = Enrollment.objects.filter(
                course_section=activity.course_section,
                student=request.user,
                is_active=True,
            ).exists()
            if not enrolled:
                return Response({"detail": "You are not enrolled in this activity's course section."}, status=status.HTTP_403_FORBIDDEN)

            # Get the student's submission for this activity (if any)
            student_submission = Submission.objects.filter(
                activity=activity,
                student=request.user,
            ).order_by('-submitted_at').first()
            student_submission_id = student_submission.id if student_submission else None

            # Build filter for comments visible to this student:
            # 1. Comments authored by this student
            # 2. Comments authored by the course section teacher
            # 3. Comments specifically on this student's submission (if they have one)
            visible_filter = Q(author=request.user) | Q(author_id=teacher_id)

            # If student has a submission, also include comments on that submission
            if student_submission_id:
                visible_filter = visible_filter | Q(submission_id=student_submission_id)

            comments = ActivityComment.objects.filter(
                activity=activity,
                parent=None,
            ).filter(visible_filter).select_related('author').prefetch_related('replies__author').order_by('created_at')

            # Filter replies similarly - only include replies the student should see
            filtered_comments = []
            for comment in comments:
                filtered_comment = self._filter_comment_replies(comment, request.user.id, teacher_id, student_submission_id)
                if filtered_comment:
                    filtered_comments.append(filtered_comment)

            serializer = ActivityCommentSerializer(filtered_comments, many=True, context={'request': request})
            return Response(serializer.data)

        elif request.user.role == User.Role.TEACHER:
            # Check if teacher owns this course section
            teaches = CourseSection.objects.filter(
                id=activity.course_section_id,
                teacher=request.user,
            ).exists()
            if not teaches:
                return Response({"detail": "You are not the teacher of this course section."}, status=status.HTTP_403_FORBIDDEN)

            # Support filtering by submission_id (for submitted work) or student_id (for any student)
            submission_id = request.query_params.get('submission_id')
            student_id = request.query_params.get('student_id')

            if submission_id:
                # Filter by specific submission (for students who have submitted)
                # Verify the submission belongs to this activity
                submission = Submission.objects.filter(id=submission_id, activity=activity).first()
                if not submission:
                    return Response({"detail": "Submission not found for this activity."}, status=status.HTTP_404_NOT_FOUND)

                # Return comments for this specific submission
                comments = ActivityComment.objects.filter(
                    activity=activity,
                    submission_id=submission_id,
                    parent=None,
                ).select_related('author').prefetch_related('replies__author').order_by('created_at')

            elif student_id:
                # Filter by specific student (works even without submission)
                # Show conversation between this student and the teacher
                student_submissions = Submission.objects.filter(activity=activity, student_id=student_id)
                submission_ids = [s.id for s in student_submissions]

                # Build filter: comments by this student OR by teacher OR on student's submissions
                student_filter = Q(author_id=student_id) | Q(author_id=request.user.id)
                if submission_ids:
                    student_filter = student_filter | Q(submission_id__in=submission_ids)

                comments = ActivityComment.objects.filter(
                    activity=activity,
                    parent=None,
                ).filter(student_filter).select_related('author').prefetch_related('replies__author').order_by('created_at')

                # Also filter replies to only show student-teacher conversation
                filtered_comments = []
                for comment in comments:
                    filtered_comment = self._filter_comment_replies_for_teacher(comment, student_id, request.user.id, submission_ids)
                    if filtered_comment:
                        filtered_comments.append(filtered_comment)

                serializer = ActivityCommentSerializer(filtered_comments, many=True, context={'request': request})
                return Response(serializer.data)

            else:
                # Teachers see all comments for their course sections
                comments = ActivityComment.objects.filter(
                    activity=activity,
                    parent=None,
                ).select_related('author').prefetch_related('replies__author').order_by('created_at')

            serializer = ActivityCommentSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data)

        elif request.user.role == User.Role.ADMIN:
            # Admins see all comments
            comments = ActivityComment.objects.filter(
                activity=activity,
                parent=None,
            ).select_related('author').prefetch_related('replies__author').order_by('created_at')

            serializer = ActivityCommentSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data)

        return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

    def _filter_comment_replies(self, comment, student_id, teacher_id, submission_id):
        """Filter replies to only include those the student should see."""
        visible_replies = []
        for reply in comment.replies.all():
            # Show reply if:
            # 1. Reply is by the student
            # 2. Reply is by the teacher
            # 3. Reply is on the student's submission (if they have one)
            is_by_student = str(reply.author_id) == str(student_id)
            is_by_teacher = str(reply.author_id) == str(teacher_id)
            is_on_student_submission = submission_id and str(reply.submission_id) == str(submission_id)

            if is_by_student or is_by_teacher or is_on_student_submission:
                visible_replies.append(reply)

        # Set filtered replies
        comment.replies._data = visible_replies
        return comment

    def _filter_comment_replies_for_teacher(self, comment, student_id, teacher_id, submission_ids):
        """Filter replies to only show student-teacher conversation."""
        visible_replies = []
        for reply in comment.replies.all():
            # Show reply if:
            # 1. Reply is by the student
            # 2. Reply is by the teacher
            # 3. Reply is on one of the student's submissions
            is_by_student = str(reply.author_id) == str(student_id)
            is_by_teacher = str(reply.author_id) == str(teacher_id)
            is_on_student_submission = submission_ids and str(reply.submission_id) in [str(sid) for sid in submission_ids]

            if is_by_student or is_by_teacher or is_on_student_submission:
                visible_replies.append(reply)

        # Set filtered replies
        comment.replies._data = visible_replies
        return comment


__all__ = [
    'ActivitySubmitView',
    'ActivityMySubmissionView',
    'ActivitySubmissionsForTeacherView',
    'ActivitySubmissionGradeView',
    'ActivityCommentViewSet',
    'ActivityCommentsByActivityView',
]