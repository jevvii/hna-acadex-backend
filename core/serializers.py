from rest_framework import serializers
from .models import (
    Activity,
    ActivityComment,
    ActivityReminder,
    Announcement,
    AssignmentGroup,
    AssignmentWeight,
    CalendarEvent,
    Course,
    CourseFile,
    Enrollment,
    GradeEntry,
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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "avatar_url", "requires_setup", "full_name")

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
            "is_published",
            "created_by",
            "created_at",
            "student_count",
        )

    def get_student_count(self, obj):
        """Return the count of active student enrollments in this activity's course section."""
        return Enrollment.objects.filter(
            course_section=obj.course_section,
            is_active=True
        ).count()


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

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_points(self, obj):
        from django.db.models import Sum
        result = obj.questions.aggregate(total=Sum('points'))
        return result['total'] if result['total'] is not None else 0

    def get_student_count(self, obj):
        """Return the count of active student enrollments in this quiz's course section."""
        return Enrollment.objects.filter(
            course_section=obj.course_section,
            is_active=True
        ).count()


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

        if reminder_type == 'activity' and not activity:
            raise serializers.ValidationError(
                {"activity_id": "Activity reminder must have an activity_id."}
            )
        if reminder_type == 'quiz' and not quiz:
            raise serializers.ValidationError(
                {"quiz_id": "Quiz reminder must have a quiz_id."}
            )
        return data

    def get_course_section_id(self, obj: ActivityReminder):
        if obj.activity_id:
            return str(obj.activity.course_section_id) if obj.activity else None
        if obj.quiz_id:
            return str(obj.quiz.course_section_id) if obj.quiz else None
        return None

    def get_activity_title(self, obj: ActivityReminder):
        if obj.reminder_type == "activity" and obj.activity:
            return obj.activity.title
        if obj.reminder_type == "quiz" and obj.quiz:
            return obj.quiz.title
        return None

    def get_activity_deadline(self, obj: ActivityReminder):
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
        read_only_fields = ("id", "activity_id", "submission_id", "author_id", "author_name", "author_avatar", "created_at", "updated_at")

    def get_author_avatar(self, obj: ActivityComment):
        """Get the author's avatar URL."""
        request = self.context.get("request")
        if obj.author.avatar_url:
            return obj.author.avatar_url
        if obj.author.avatar:
            url = obj.author.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_replies(self, obj: ActivityComment):
        """Get nested replies for this comment."""
        # Only include replies if we're not already in a nested context
        # to prevent infinite recursion
        if self.context.get('include_replies', True):
            replies = obj.replies.all()
            # Set include_replies to False for nested replies to prevent recursion
            context = {**self.context, 'include_replies': False}
            return ActivityCommentSerializer(replies, many=True, context=context).data
        return []


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
