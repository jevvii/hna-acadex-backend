from rest_framework import serializers
from .models import (
    Activity,
    Announcement,
    AssignmentGroup,
    CalendarEvent,
    Course,
    CourseFile,
    Notification,
    MeetingSession,
    AttendanceRecord,
    PasswordResetRequest,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    Section,
    Submission,
    TodoItem,
    User,
    WeeklyModule,
)


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "avatar_url", "requires_setup")

    def get_avatar_url(self, obj: User):
        request = self.context.get("request")
        if obj.avatar_url:
            return obj.avatar_url
        if obj.avatar:
            url = obj.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
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
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class TodoItemSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    activity_id = serializers.UUIDField(read_only=True)
    quiz_id = serializers.UUIDField(read_only=True)
    course_section_id = serializers.SerializerMethodField()

    def get_course_section_id(self, obj: TodoItem):
        if obj.activity_id:
            return str(obj.activity.course_section_id) if obj.activity else None
        if obj.quiz_id:
            return str(obj.quiz.course_section_id) if obj.quiz else None
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
        fields = "__all__"


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = "__all__"


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
            "weekly_module_id",
            "assignment_group_id",
            "allowed_file_types",
            "support_file_url",
            "is_published",
            "created_by",
            "created_at",
        )


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

    class Meta:
        model = Quiz
        fields = (
            "id",
            "course_section_id",
            "title",
            "instructions",
            "time_limit_minutes",
            "attempt_limit",
            "open_at",
            "close_at",
            "weekly_module_id",
            "is_published",
            "shuffle_questions",
            "shuffle_choices",
            "show_results",
            "created_at",
        )


class SubmissionSerializer(serializers.ModelSerializer):
    activity_id = serializers.UUIDField(read_only=True)
    student_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Submission
        fields = (
            "id",
            "activity_id",
            "student_id",
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
        fields = ("id", "quiz_id", "question_text", "question_type", "points", "sort_order", "choices")

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


class QuizAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_choice_id = serializers.UUIDField(required=False, allow_null=True)
    text_answer = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class QuizAnswerGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAnswer
        fields = ("points_awarded", "is_correct")


class PasswordResetRequestSerializer(serializers.ModelSerializer):
    """Serializer for password reset requests (admin view)."""
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.full_name", read_only=True)

    class Meta:
        model = PasswordResetRequest
        fields = (
            "id",
            "user",
            "user_email",
            "user_name",
            "personal_email",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by",
            "resolved_by_name",
        )
        read_only_fields = ("id", "user", "created_at", "resolved_at", "resolved_by")


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
