import logging
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from .comment_crypto import decrypt_comment_content
from .models import (
    Activity,
    ActivityComment,
    ActivityReminder,
    AdviserOverrideLog,
    Announcement,
    AssignmentGroup,
    AssignmentWeight,
    CalendarEvent,
    Course,
    CourseFile,
    Enrollment,
    GradeEntry,
    GradeSubmission,
    GradeWeightConfig,
    GradingPeriod,
    Notification,
    MeetingSession,
    AttendanceRecord,
    PasswordResetRequest,
    PushToken,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    Section,
    SectionReportCard,
    Submission,
    TodoItem,
    User,
    WeeklyModule,
)


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    advisory_section_id = serializers.SerializerMethodField()
    advisory_section_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "last_name",
            "middle_name",
            "full_name",
            "email",
            "role",
            "status",
            "avatar_url",
            "grade_level",
            "strand",
            "section",
            "employee_id",
            "student_id",
            "theme",
            "requires_setup",
            "advisory_section_id",
            "advisory_section_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "avatar_url", "requires_setup", "full_name", "advisory_section_id", "advisory_section_name")

    def get_avatar_url(self, obj: User) -> str | None:
        request = self.context.get("request")
        if obj.avatar_url:
            if request and obj.avatar_url.startswith("/"):
                return request.build_absolute_uri(obj.avatar_url)
            return obj.avatar_url
        if obj.avatar:
            url = obj.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_advisory_section_id(self, obj: User) -> str | None:
        from .models import TeacherAdvisory
        advisory = TeacherAdvisory.objects.filter(
            teacher=obj, is_active=True
        ).select_related('section').first()
        return str(advisory.section.id) if advisory else None

    def get_advisory_section_name(self, obj: User) -> str | None:
        from .models import TeacherAdvisory
        advisory = TeacherAdvisory.objects.filter(
            teacher=obj, is_active=True
        ).select_related('section').first()
        return f"{advisory.section.name}" if advisory else None


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "last_name",
            "middle_name",
            "full_name",
            "email",
            "password",
            "role",
            "status",
            "grade_level",
            "strand",
            "section",
            "employee_id",
            "student_id",
            "theme",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "full_name")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class TodoItemSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    activity_id = serializers.UUIDField(read_only=True)
    quiz_id = serializers.UUIDField(read_only=True)
    course_section_id = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()
    is_generated = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    target_path = serializers.SerializerMethodField()

    def get_course_section_id(self, obj: TodoItem) -> str | None:
        if obj.activity_id:
            return str(obj.activity.course_section_id) if obj.activity else None
        if obj.quiz_id:
            return str(obj.quiz.course_section_id) if obj.quiz else None
        return None

    def get_source_type(self, obj: TodoItem) -> str:
        if obj.activity_id:
            return "activity"
        if obj.quiz_id:
            return "quiz"
        return "manual"

    def get_is_generated(self, obj: TodoItem) -> bool:
        return bool(obj.activity_id or obj.quiz_id)

    def _availability_state(self, obj: TodoItem) -> tuple[bool, bool]:
        if obj.is_done:
            return False, True

        if obj.activity_id:
            if not obj.activity:
                return True, False
            if (
                obj.activity.deadline
                and timezone.now() > obj.activity.deadline
                and not obj.activity.allow_late_submissions
            ):
                return True, False
            return False, True

        if obj.quiz_id:
            if not obj.quiz:
                return True, False
            now = timezone.now()
            if obj.quiz.open_at and now < obj.quiz.open_at:
                return True, False
            if obj.quiz.close_at and now > obj.quiz.close_at:
                return True, False
            return False, True

        return False, True

    def get_is_locked(self, obj: TodoItem) -> bool:
        locked, _available = self._availability_state(obj)
        return locked

    def get_is_available(self, obj: TodoItem) -> bool:
        _locked, available = self._availability_state(obj)
        return available

    def get_target_path(self, obj: TodoItem) -> str | None:
        if obj.activity_id:
            return f"/activities/{obj.activity_id}"
        if obj.quiz_id:
            return f"/quizzes/{obj.quiz_id}"
        return None

    class Meta:
        model = TodoItem
        fields = (
            "id",
            "user_id",
            "title",
            "description",
            "due_at",
            "is_done",
            "activity_id",
            "quiz_id",
            "course_section_id",
            "source_type",
            "is_generated",
            "is_locked",
            "is_available",
            "target_path",
            "completed_at",
            "created_at",
        )
        read_only_fields = ("id", "user_id", "created_at")


class CalendarEventSerializer(serializers.ModelSerializer):
    creator_id = serializers.UUIDField(read_only=True)
    course_section_id = serializers.UUIDField(read_only=True)
    activity_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CalendarEvent
        fields = (
            "id",
            "creator_id",
            "course_section_id",
            "activity_id",
            "title",
            "description",
            "event_type",
            "start_at",
            "end_at",
            "all_day",
            "color",
            "is_personal",
        )
        read_only_fields = ("id", "creator_id")

    def validate_event_type(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user
            and getattr(user, "is_authenticated", False)
            and user.role in {User.Role.STUDENT, User.Role.TEACHER}
            and value == CalendarEvent.EventType.HOLIDAY
        ):
            raise serializers.ValidationError(
                "Holiday events are system-managed and cannot be added manually."
            )
        return value


class NotificationSerializer(serializers.ModelSerializer):
    recipient_id = serializers.UUIDField(read_only=True)
    course_section_id = serializers.UUIDField(read_only=True)
    activity_id = serializers.UUIDField(read_only=True)
    quiz_id = serializers.UUIDField(read_only=True)
    announcement_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient_id",
            "type",
            "title",
            "body",
            "course_section_id",
            "activity_id",
            "quiz_id",
            "announcement_id",
            "is_read",
            "created_at",
        )
        read_only_fields = ("id", "recipient_id", "created_at")


class MeetingSessionSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = MeetingSession
        fields = (
            "id",
            "course_section_id",
            "date",
            "title",
            "created_by_id",
            "created_at",
        )


class AttendanceRecordSerializer(serializers.ModelSerializer):
    meeting_id = serializers.UUIDField()
    student_id = serializers.UUIDField()
    marked_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "meeting_id",
            "student_id",
            "status",
            "remarks",
            "marked_by_id",
            "updated_at",
            "created_at",
        )


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name', 'grade_level', 'strand', 'school_year', 'is_active', 'created_at', 'updated_at']


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'code', 'title', 'description', 'cover_image_url', 'color_overlay', 'grade_level', 'strand', 'category', 'school_year', 'semester', 'num_weeks', 'is_active', 'created_at', 'updated_at']


class WeeklyModuleSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()

    class Meta:
        model = WeeklyModule
        fields = (
            "id",
            "course_section_id",
            "week_number",
            "title",
            "description",
            "is_exam_week",
            "is_published",
            "sort_order",
        )


class ActivitySerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()
    created_by = serializers.UUIDField(source="created_by_id", read_only=True)
    weekly_module_id = serializers.UUIDField(allow_null=True, required=False)
    assignment_group_id = serializers.UUIDField(allow_null=True, required=False)
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = (
            "id",
            "course_section_id",
            "title",
            "description",
            "instructions",
            "points",
            "deadline",
            "allow_late_submissions",
            "weekly_module_id",
            "assignment_group_id",
            "allowed_file_types",
            "support_file_url",
            "attempt_limit",
            "score_selection_policy",
            "component_type",
            "is_exam",
            "exam_type",
            "is_published",
            "created_by",
            "created_at",
            "student_count",
        )

    def get_student_count(self, obj: Activity) -> int:
        """Return the count of active student enrollments in this activity's course section."""
        return Enrollment.objects.filter(
            course_section=obj.course_section,
            is_active=True
        ).count()

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        course_section_id = attrs.get("course_section_id") or (str(instance.course_section_id) if instance else None)
        weekly_module_id = attrs.get("weekly_module_id")
        if weekly_module_id is None and instance is not None:
            weekly_module_id = str(instance.weekly_module_id) if instance.weekly_module_id else None

        if not weekly_module_id:
            raise serializers.ValidationError({"weekly_module_id": "Week topic is required."})

        if course_section_id and not WeeklyModule.objects.filter(
            id=weekly_module_id,
            course_section_id=course_section_id,
        ).exists():
            raise serializers.ValidationError(
                {"weekly_module_id": "Selected week/topic does not belong to this course section."}
            )

        assignment_group_id = attrs.get("assignment_group_id")
        if assignment_group_id is None and instance is not None:
            assignment_group_id = str(instance.assignment_group_id) if instance.assignment_group_id else None
        if assignment_group_id and course_section_id and not AssignmentGroup.objects.filter(
            id=assignment_group_id,
            course_section_id=course_section_id,
        ).exists():
            raise serializers.ValidationError(
                {"assignment_group_id": "Selected assignment group does not belong to this course section."}
            )

        is_exam = attrs.get("is_exam")
        if is_exam is None and instance is not None:
            is_exam = bool(instance.is_exam)
        exam_type = attrs.get("exam_type")
        if exam_type is None and instance is not None:
            exam_type = instance.exam_type
        component_type = attrs.get("component_type")
        if component_type is None and instance is not None:
            component_type = instance.component_type

        if is_exam:
            if exam_type not in [Activity.ExamType.MONTHLY, Activity.ExamType.QUARTERLY]:
                raise serializers.ValidationError({"exam_type": "Exam type is required for exam activities."})
        elif component_type not in [Activity.ComponentType.WRITTEN_WORKS, Activity.ComponentType.PERFORMANCE_TASK]:
            raise serializers.ValidationError(
                {"component_type": "Component type must be Written Works or Performance Task for non-exam activities."}
            )

        return attrs


class AssignmentGroupSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()

    class Meta:
        model = AssignmentGroup
        fields = ("id", "course_section_id", "name", "weight_percent", "is_active", "created_at")


class CourseFileSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()
    uploader_id = serializers.UUIDField(read_only=True)
    weekly_module_id = serializers.UUIDField(allow_null=True, required=False)
    file_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = CourseFile
        fields = (
            "id",
            "course_section_id",
            "weekly_module_id",
            "uploader_id",
            "file_name",
            "file_url",
            "preview_file_url",
            "file_type",
            "file_size_bytes",
            "category",
            "folder_path",
            "is_visible",
            "created_at",
        )

    logger = logging.getLogger(__name__)

    _CLOUDINARY_URL_PATTERN = re.compile(
        r"^/[^/]+/(?P<resource_type>image|raw|video)/(?P<delivery_type>upload|private|authenticated)"
        r"(?:/s--[^/]+--)?"  # optional signature component
        r"(?:/v(?P<version>\d+))?"
        r"/(?P<public_id>.+)$"
    )

    def _build_cloudinary_delivery_url(self, original_url: str | None) -> str | None:
        if not original_url:
            return original_url

        parsed = urlparse(original_url)
        if parsed.netloc.lower() != "res.cloudinary.com":
            return original_url

        match = self._CLOUDINARY_URL_PATTERN.match(parsed.path)
        if not match:
            self.logger.warning("cloudinary_url_no_match: url=%s", original_url)
            return original_url

        resource_type = match.group("resource_type")
        delivery_type = match.group("delivery_type")
        public_id = match.group("public_id")
        version_str = match.group("version")
        version = int(version_str) if version_str else None

        if not all([
            getattr(settings, "CLOUDINARY_CLOUD_NAME", None),
            getattr(settings, "CLOUDINARY_API_KEY", None),
            getattr(settings, "CLOUDINARY_API_SECRET", None),
        ]):
            self.logger.warning("cloudinary_sign_skip: missing credentials, returning unsigned url")
            return original_url

        try:
            from cloudinary.utils import cloudinary_url
        except Exception:
            return original_url

        try:
            auth_token_key = getattr(settings, "CLOUDINARY_AUTH_TOKEN_KEY", None)
            sign_kwargs = dict(
                resource_type=resource_type,
                type=delivery_type,
                secure=True,
                sign_url=True,
            )
            if version is not None:
                sign_kwargs["version"] = version
            if auth_token_key:
                sign_kwargs["auth_token"] = {"key": auth_token_key, "duration": 3600}
            signed_url, _ = cloudinary_url(public_id, **sign_kwargs)
            import cloudinary as _cloudinary
            self.logger.info(
                "cloudinary_sign: original=%s signed=%s public_id=%s resource_type=%s delivery_type=%s version=%s auth_token=%s cloud_name=%s",
                original_url, signed_url, public_id, resource_type, delivery_type, version,
                bool(auth_token_key),
                getattr(_cloudinary.config(), "cloud_name", "?"),
            )
            return signed_url
        except Exception:
            self.logger.exception("cloudinary_sign_error: failed to sign url=%s", original_url)
            return original_url

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["file_url"] = self._build_cloudinary_delivery_url(data.get("file_url"))
        data["preview_file_url"] = self._build_cloudinary_delivery_url(data.get("preview_file_url"))
        return data


class AnnouncementSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()
    created_by = serializers.UUIDField(source="created_by_id", read_only=True)

    class Meta:
        model = Announcement
        fields = (
            "id",
            "course_section_id",
            "school_wide",
            "audience",
            "title",
            "body",
            "attachment_urls",
            "created_by",
            "scheduled_at",
            "is_published",
            "created_at",
        )


class QuizSerializer(serializers.ModelSerializer):
    course_section_id = serializers.UUIDField()
    weekly_module_id = serializers.UUIDField(allow_null=True, required=False)
    question_count = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course_section_id",
            "title",
            "instructions",
            "time_limit_minutes",
            "attempt_limit",
            "score_selection_policy",
            "open_at",
            "close_at",
            "weekly_module_id",
            "is_published",
            "shuffle_questions",
            "shuffle_choices",
            "show_results",
            "created_at",
            "question_count",
            "points",
            "student_count",
        )

    def get_question_count(self, obj: Quiz) -> int:
        return obj.questions.count()

    def get_points(self, obj: Quiz) -> int | float:
        from django.db.models import Sum
        result = obj.questions.aggregate(total=Sum('points'))
        return result['total'] if result['total'] is not None else 0

    def get_student_count(self, obj: Quiz) -> int:
        """Return the count of active student enrollments in this quiz's course section."""
        return Enrollment.objects.filter(
            course_section=obj.course_section,
            is_active=True
        ).count()

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        course_section_id = attrs.get("course_section_id") or (str(instance.course_section_id) if instance else None)
        weekly_module_id = attrs.get("weekly_module_id")
        if weekly_module_id is None and instance is not None:
            weekly_module_id = str(instance.weekly_module_id) if instance.weekly_module_id else None

        if not weekly_module_id:
            raise serializers.ValidationError({"weekly_module_id": "Week topic is required."})

        if course_section_id and not WeeklyModule.objects.filter(
            id=weekly_module_id,
            course_section_id=course_section_id,
        ).exists():
            raise serializers.ValidationError(
                {"weekly_module_id": "Selected week/topic does not belong to this course section."}
            )

        return attrs


class SubmissionSerializer(serializers.ModelSerializer):
    activity_id = serializers.UUIDField(read_only=True)
    student_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Submission
        fields = (
            "id",
            "activity_id",
            "student_id",
            "attempt_number",
            "file_urls",
            "text_content",
            "status",
            "score",
            "feedback",
            "submitted_at",
            "graded_at",
            "created_at",
            "updated_at",
        )


class SubmissionGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = ("score", "feedback", "status")


class QuizChoiceStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizChoice
        fields = ("id", "choice_text", "sort_order")


class QuizChoiceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizChoice
        fields = ("id", "choice_text", "is_correct", "sort_order")


class QuizQuestionStudentSerializer(serializers.ModelSerializer):
    choices = QuizChoiceStudentSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "question_text", "question_type", "points", "sort_order", "choices")


class QuizQuestionWriteSerializer(serializers.ModelSerializer):
    choices = QuizChoiceWriteSerializer(many=True, required=False)
    quiz_id = serializers.UUIDField()

    class Meta:
        model = QuizQuestion
        fields = (
            "id", "quiz_id", "question_text", "question_type", "points", "sort_order", "choices",
            "correct_answer", "alternate_answers", "case_sensitive", "word_limit"
        )

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        question_type = attrs.get("question_type") or (instance.question_type if instance else None)

        if question_type == QuizQuestion.QuestionType.IDENTIFICATION:
            correct_answer = attrs.get("correct_answer")
            if correct_answer is None and instance is not None:
                correct_answer = instance.correct_answer
            if not str(correct_answer or "").strip():
                raise serializers.ValidationError(
                    {"correct_answer": "Correct answer is required for identification questions."}
                )

        return attrs

    def create(self, validated_data):
        choices_data = validated_data.pop("choices", [])
        question = QuizQuestion.objects.create(**validated_data)
        for idx, choice in enumerate(choices_data):
            choice_data = dict(choice)
            sort_order = choice_data.pop("sort_order", idx)
            QuizChoice.objects.create(question=question, sort_order=sort_order, **choice_data)
        return question

    def update(self, instance, validated_data):
        choices_data = validated_data.pop("choices", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if choices_data is not None:
            instance.choices.all().delete()
            for idx, choice in enumerate(choices_data):
                choice_data = dict(choice)
                sort_order = choice_data.pop("sort_order", idx)
                QuizChoice.objects.create(question=instance, sort_order=sort_order, **choice_data)
        return instance


class QuizQuestionBulkSerializer(serializers.Serializer):
    """Serializer for bulk question upsert operations."""
    questions = QuizQuestionWriteSerializer(many=True)


class QuizAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_choice_id = serializers.UUIDField(required=False, allow_null=True)
    selected_choice_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    text_answer = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class QuizAnswerGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAnswer
        fields = ("points_awarded", "is_correct")


class PasswordResetRequestSerializer(serializers.ModelSerializer):
    """Serializer for password reset requests (admin view)."""
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.full_name", read_only=True, allow_null=True)

    class Meta:
        model = PasswordResetRequest
        fields = (
            "id",
            "user_email",
            "user_name",
            "personal_email",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by_name",
        )
        read_only_fields = ("id", "created_at", "resolved_at", "resolved_by_name")


class PushTokenSerializer(serializers.ModelSerializer):
    """Serializer for push notification tokens."""
    user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PushToken
        fields = (
            "id",
            "user_id",
            "token",
            "device_type",
            "device_name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user_id", "created_at", "updated_at")


class ActivityReminderSerializer(serializers.ModelSerializer):
    """Serializer for activity/quiz reminders."""
    user_id = serializers.UUIDField(read_only=True)
    # Accept activity_id/quiz_id on write (mapped to foreign keys),
    # and return them as UUIDs on read (using the same field name for backward compat)
    activity_id = serializers.PrimaryKeyRelatedField(
        queryset=Activity.objects.all(),
        source='activity',
        required=False,
        allow_null=True,
    )
    quiz_id = serializers.PrimaryKeyRelatedField(
        queryset=Quiz.objects.all(),
        source='quiz',
        required=False,
        allow_null=True,
    )
    course_section_id = serializers.SerializerMethodField()
    activity_title = serializers.SerializerMethodField()
    activity_deadline = serializers.SerializerMethodField()

    class Meta:
        model = ActivityReminder
        fields = (
            "id",
            "user_id",
            "reminder_type",
            "activity_id",
            "quiz_id",
            "course_section_id",
            "activity_title",
            "activity_deadline",
            "reminder_datetime",
            "offset_minutes",
            "notification_sent",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user_id", "notification_sent", "created_at", "updated_at")

    def validate(self, data):
        """Validate that the reminder has a valid target based on reminder_type."""
        reminder_type = data.get('reminder_type')
        activity = data.get('activity')
        quiz = data.get('quiz')
        reminder_datetime = data.get('reminder_datetime')

        if reminder_type == 'activity' and not activity:
            raise serializers.ValidationError(
                {"activity_id": "Activity reminder must have an activity_id."}
            )
        if reminder_type == 'quiz' and not quiz:
            raise serializers.ValidationError(
                {"quiz_id": "Quiz reminder must have a quiz_id."}
            )

        deadline = None
        if reminder_type == 'activity' and activity:
            deadline = activity.deadline
        if reminder_type == 'quiz' and quiz:
            deadline = quiz.close_at

        if not deadline:
            raise serializers.ValidationError(
                {"reminder_datetime": "A reminder requires a valid deadline."}
            )

        now = timezone.now()
        if deadline <= now:
            raise serializers.ValidationError(
                {"reminder_datetime": "The deadline has already passed. Reminders are no longer available."}
            )
        if reminder_datetime and reminder_datetime < now:
            raise serializers.ValidationError(
                {"reminder_datetime": "Reminder time must be now or later."}
            )
        if reminder_datetime and reminder_datetime > deadline:
            raise serializers.ValidationError(
                {"reminder_datetime": "Reminder time must not be later than the deadline."}
            )
        return data

    def get_course_section_id(self, obj: ActivityReminder) -> str | None:
        if obj.activity_id:
            return str(obj.activity.course_section_id) if obj.activity else None
        if obj.quiz_id:
            return str(obj.quiz.course_section_id) if obj.quiz else None
        return None

    def get_activity_title(self, obj: ActivityReminder) -> str | None:
        if obj.reminder_type == "activity" and obj.activity:
            return obj.activity.title
        if obj.reminder_type == "quiz" and obj.quiz:
            return obj.quiz.title
        return None

    def get_activity_deadline(self, obj: ActivityReminder) -> datetime | None:
        if obj.reminder_type == "activity" and obj.activity:
            return obj.activity.deadline
        if obj.reminder_type == "quiz" and obj.quiz:
            return obj.quiz.close_at
        return None



class ActivityCommentSerializer(serializers.ModelSerializer):
    """Serializer for activity comments with author details and nested replies."""
    id = serializers.UUIDField(read_only=True)
    activity_id = serializers.UUIDField(read_only=True)
    submission_id = serializers.UUIDField(read_only=True, allow_null=True)
    thread_student_id = serializers.UUIDField(read_only=True, allow_null=True)
    author_id = serializers.UUIDField(source='author.id', read_only=True)
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    author_avatar = serializers.SerializerMethodField()
    parent_id = serializers.UUIDField(source='parent.id', read_only=True, allow_null=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = ActivityComment
        fields = (
            "id",
            "activity_id",
            "submission_id",
            "thread_student_id",
            "author_id",
            "author_name",
            "author_avatar",
            "parent_id",
            "content",
            "file_urls",
            "created_at",
            "updated_at",
            "replies",
        )
        read_only_fields = ("id", "activity_id", "submission_id", "thread_student_id", "author_id", "author_name", "author_avatar", "created_at", "updated_at")

    def get_author_avatar(self, obj: ActivityComment) -> str | None:
        """Get the author's avatar URL."""
        request = self.context.get("request")
        if obj.author.avatar_url:
            return obj.author.avatar_url
        if obj.author.avatar:
            url = obj.author.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_replies(self, obj: ActivityComment) -> list[dict[str, Any]]:
        """Get nested replies for this comment."""
        # Only include replies if we're not already in a nested context
        # to prevent infinite recursion
        if self.context.get('include_replies', True):
            replies = getattr(obj, "_visible_replies", obj.replies.all())
            # Set include_replies to False for nested replies to prevent recursion
            context = {**self.context, 'include_replies': False}
            return ActivityCommentSerializer(replies, many=True, context=context).data
        return []

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["content"] = decrypt_comment_content(instance.content)
        return data


class GradingPeriodSerializer(serializers.ModelSerializer):
    """Serializer for GradingPeriod model."""
    label = serializers.ReadOnlyField()

    class Meta:
        model = GradingPeriod
        fields = (
            'id',
            'school_year',
            'period_type',
            'period_number',
            'label',
            'start_date',
            'end_date',
            'is_current',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'label')


class GradeEntrySerializer(serializers.ModelSerializer):
    """Serializer for GradeEntry model."""
    period_label = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='enrollment.student.get_full_name', read_only=True)
    course_section_id = serializers.UUIDField(source='enrollment.course_section_id', read_only=True)

    class Meta:
        model = GradeEntry
        fields = (
            'id',
            'enrollment_id',
            'grading_period_id',
            'course_section_id',
            'student_name',
            'period_label',
            'score',
            'computed_score',
            'override_score',
            'is_published',
            'computed_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'computed_score', 'computed_at', 'created_at', 'updated_at')

    def get_period_label(self, obj):
        return obj.grading_period.label


class AssignmentWeightSerializer(serializers.ModelSerializer):
    """Serializer for AssignmentWeight model."""

    class Meta:
        model = AssignmentWeight
        fields = (
            'id',
            'course_section_id',
            'grading_period_id',
            'category',
            'weight_percent',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class GradingPeriodSerializer(serializers.ModelSerializer):
    """Serializer for GradingPeriod model."""
    label = serializers.ReadOnlyField()

    class Meta:
        model = GradingPeriod
        fields = (
            "id",
            "school_year",
            "period_type",
            "period_number",
            "label",
            "start_date",
            "end_date",
            "is_current",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class GradeEntrySerializer(serializers.ModelSerializer):
    """Serializer for GradeEntry model."""
    period_label = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    course_section_id = serializers.SerializerMethodField()
    course_code = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()

    class Meta:
        model = GradeEntry
        fields = (
            "id",
            "enrollment",
            "grading_period",
            "period_label",
            "computed_score",
            "override_score",
            "score",
            "is_published",
            "student_name",
            "course_section_id",
            "course_code",
            "course_title",
            "computed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "computed_at", "created_at", "updated_at")

    def get_period_label(self, obj):
        return obj.grading_period.label

    def get_student_name(self, obj):
        return obj.enrollment.student.get_full_name()

    def get_course_section_id(self, obj):
        return str(obj.enrollment.course_section_id)

    def get_course_code(self, obj):
        return obj.enrollment.course_section.course.code

    def get_course_title(self, obj):
        return obj.enrollment.course_section.course.title


class AssignmentWeightSerializer(serializers.ModelSerializer):
    """Serializer for AssignmentWeight model."""

    class Meta:
        model = AssignmentWeight
        fields = (
            "id",
            "course_section",
            "grading_period",
            "category",
            "weight_percent",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class GradeWeightConfigSerializer(serializers.ModelSerializer):
    """Serializer for GradeWeightConfig with computed subject category info."""
    subject_category = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = GradeWeightConfig
        fields = [
            'id', 'course_section', 'written_works', 'performance_tasks',
            'quarterly_assessment', 'is_customized', 'subject_category',
            'category_label', 'updated_at',
        ]
        read_only_fields = ['id', 'course_section', 'is_customized', 'updated_at']

    def get_subject_category(self, obj):
        return obj.course_section.course.category

    def get_category_label(self, obj):
        cat = obj.course_section.course.category
        if cat:
            return dict(Course.SubjectCategory.choices).get(cat, cat)
        return None


class GradeSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeSubmission
        fields = ['id', 'course_section', 'grading_period', 'submitted_by', 'submitted_at', 'taken_back_at', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'submitted_by', 'submitted_at', 'taken_back_at', 'created_at', 'updated_at']


class SectionReportCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = SectionReportCard
        fields = ['id', 'section', 'grading_period', 'published_by', 'published_at', 'is_published', 'created_at', 'updated_at']
        read_only_fields = ['id', 'published_by', 'published_at', 'created_at', 'updated_at']


class AdviserOverrideLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdviserOverrideLog
        fields = ['id', 'grade_entry', 'adviser', 'previous_score', 'new_score', 'created_at']
        read_only_fields = ['id', 'adviser', 'created_at']
