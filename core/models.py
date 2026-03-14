# hna-acadex-backend/core/models.py
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class GradeLevel(models.TextChoices):
        G7 = "Grade 7", "Grade 7"
        G8 = "Grade 8", "Grade 8"
        G9 = "Grade 9", "Grade 9"
        G10 = "Grade 10", "Grade 10"
        G11 = "Grade 11", "Grade 11"
        G12 = "Grade 12", "Grade 12"

    class Strand(models.TextChoices):
        STEM = "STEM", "STEM"
        ABM = "ABM", "ABM"
        HUMSS = "HUMSS", "HUMSS"
        TVL = "TVL", "TVL"
        GAS = "GAS", "GAS"
        NONE = "NONE", "NONE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    personal_email = models.EmailField(blank=True, null=True, help_text="Personal email for sending login credentials")
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    avatar = models.FileField(upload_to="avatars/", blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)
    grade_level = models.CharField(max_length=20, choices=GradeLevel.choices, blank=True, null=True)
    strand = models.CharField(max_length=10, choices=Strand.choices, default=Strand.NONE)
    section = models.CharField(max_length=100, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    student_id = models.CharField(max_length=50, blank=True, null=True)
    theme = models.CharField(max_length=20, default="system")
    requires_setup = models.BooleanField(default=True, help_text="User must complete first-time setup (photo + password)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.email})"


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    grade_level = models.CharField(max_length=20, choices=User.GradeLevel.choices)
    strand = models.CharField(max_length=10, choices=User.Strand.choices, default=User.Strand.NONE)
    school_year = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.school_year})"


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    cover_image_url = models.URLField(blank=True, null=True)
    color_overlay = models.CharField(max_length=20, blank=True, null=True)
    grade_level = models.CharField(max_length=20, choices=User.GradeLevel.choices, blank=True, null=True)
    strand = models.CharField(max_length=10, choices=User.Strand.choices, blank=True, null=True)
    school_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20, blank=True, null=True)
    num_weeks = models.PositiveIntegerField(default=18)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.title}"


class CourseSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="course_sections")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="course_sections")
    teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_course_sections",
        limit_choices_to={"role": User.Role.TEACHER},
    )
    school_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("course", "section", "school_year", "semester")

    def __str__(self):
        return f"{self.course.code}@{self.section.name}"


class Enrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="enrollments")
    final_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    manual_final_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course_section")


class WeeklyModule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="weekly_modules")
    week_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_exam_week = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)


class AssignmentGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="assignment_groups")
    name = models.CharField(max_length=100)
    weight_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("course_section", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.course_section} - {self.name}"


class Activity(models.Model):
    class ScorePolicy(models.TextChoices):
        LATEST = "latest", "Latest"
        HIGHEST = "highest", "Highest"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="activities")
    weekly_module = models.ForeignKey(
        WeeklyModule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    assignment_group = models.ForeignKey(
        AssignmentGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    instructions = models.TextField(blank=True, null=True)
    points = models.PositiveIntegerField(default=100)
    deadline = models.DateTimeField(blank=True, null=True)
    allowed_file_types = models.JSONField(blank=True, null=True)
    support_file_url = models.URLField(blank=True, null=True)
    attempt_limit = models.PositiveIntegerField(default=1)
    score_selection_policy = models.CharField(
        max_length=20,
        choices=ScorePolicy.choices,
        default=ScorePolicy.HIGHEST,
    )
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class CourseFile(models.Model):
    class Category(models.TextChoices):
        MODULE = "module", "Module"
        ASSIGNMENT = "assignment", "Assignment"
        QUIZ = "quiz", "Quiz"
        GENERAL = "general", "General"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="course_files")
    weekly_module = models.ForeignKey(
        WeeklyModule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="learning_materials",
    )
    uploader = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    file_name = models.CharField(max_length=255)
    file_url = models.URLField()
    preview_file_url = models.URLField(blank=True, null=True)
    file_type = models.CharField(max_length=30, blank=True, null=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    folder_path = models.CharField(max_length=255, default="/")
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Quiz(models.Model):
    class ScorePolicy(models.TextChoices):
        LATEST = "latest", "Latest"
        HIGHEST = "highest", "Highest"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="quizzes")
    weekly_module = models.ForeignKey(
        WeeklyModule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quizzes",
    )
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True, null=True)
    time_limit_minutes = models.PositiveIntegerField(blank=True, null=True)
    attempt_limit = models.PositiveIntegerField(default=1)
    score_selection_policy = models.CharField(
        max_length=20,
        choices=ScorePolicy.choices,
        default=ScorePolicy.HIGHEST,
    )
    open_at = models.DateTimeField(blank=True, null=True)
    close_at = models.DateTimeField(blank=True, null=True)
    is_published = models.BooleanField(default=True)
    shuffle_questions = models.BooleanField(default=False)
    shuffle_choices = models.BooleanField(default=False)
    show_results = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Announcement(models.Model):
    class Audience(models.TextChoices):
        TEACHERS_ONLY = "teachers_only", "Teachers Only"
        ALL = "all", "All"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, null=True, blank=True, on_delete=models.CASCADE, related_name="announcements")
    school_wide = models.BooleanField(default=False)
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    title = models.CharField(max_length=255)
    body = models.TextField()
    attachment_urls = models.JSONField(blank=True, null=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CalendarEvent(models.Model):
    class EventType(models.TextChoices):
        DEADLINE = "deadline", "Deadline"
        EXAM = "exam", "Exam"
        PERSONAL = "personal", "Personal"
        HOLIDAY = "holiday", "Holiday"
        SCHOOL_EVENT = "school_event", "School Event"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="calendar_events")
    course_section = models.ForeignKey(CourseSection, null=True, blank=True, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name="calendar_events")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(blank=True, null=True)
    all_day = models.BooleanField(default=False)
    color = models.CharField(max_length=20, blank=True, null=True)
    is_personal = models.BooleanField(default=True)

    class Meta:
        unique_together = ("creator", "activity")


class TodoItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="todo_items")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_at = models.DateTimeField(blank=True, null=True)
    is_done = models.BooleanField(default=False)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL)
    quiz = models.ForeignKey(Quiz, null=True, blank=True, on_delete=models.SET_NULL)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("user", "activity"), ("user", "quiz"))


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        NEW_ACTIVITY = "new_activity", "New Activity"
        NEW_QUIZ = "new_quiz", "New Quiz"
        NEW_EXAM = "new_exam", "New Exam"
        GRADE_RELEASED = "grade_released", "Grade Released"
        COURSE_ANNOUNCEMENT = "course_announcement", "Course Announcement"
        SCHOOL_ANNOUNCEMENT = "school_announcement", "School Announcement"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.SYSTEM)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    course_section = models.ForeignKey(CourseSection, null=True, blank=True, on_delete=models.SET_NULL)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL)
    quiz = models.ForeignKey(Quiz, null=True, blank=True, on_delete=models.SET_NULL)
    announcement = models.ForeignKey(Announcement, null=True, blank=True, on_delete=models.SET_NULL)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class MeetingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name="meeting_sessions")
    date = models.DateField()
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]


class AttendanceRecord(models.Model):
    class AttendanceStatus(models.TextChoices):
        PRESENT = "Present", "Present"
        ABSENT = "Absent", "Absent"
        LATE = "Late", "Late"
        EXCUSED = "Excused", "Excused"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(MeetingSession, on_delete=models.CASCADE, related_name="attendance_records")
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    status = models.CharField(max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.ABSENT)
    remarks = models.TextField(blank=True, null=True)
    marked_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="marked_attendance_records")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("meeting", "student")
        ordering = ["meeting__date", "student__full_name"]


class Submission(models.Model):
    class SubmissionStatus(models.TextChoices):
        NOT_SUBMITTED = "not_submitted", "Not Submitted"
        SUBMITTED = "submitted", "Submitted"
        LATE = "late", "Late"
        GRADED = "graded", "Graded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activity_submissions",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    attempt_number = models.PositiveIntegerField(default=1)
    file_urls = models.JSONField(blank=True, null=True)
    text_content = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.SUBMITTED)
    score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    feedback = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    graded_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("activity", "student", "attempt_number")
        ordering = ["-attempt_number"]


class QuizQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"
        TRUE_FALSE = "true_false", "True/False"
        ESSAY = "essay", "Essay"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    question_type = models.CharField(max_length=30, choices=QuestionType.choices)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]


class QuizChoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="choices")
    choice_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class QuizAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    max_score = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    is_submitted = models.BooleanField(default=False)
    pending_manual_grading = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("quiz", "student", "attempt_number")
        ordering = ["-created_at"]


class QuizAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="answers")
    selected_choice = models.ForeignKey(QuizChoice, null=True, blank=True, on_delete=models.SET_NULL)
    text_answer = models.TextField(blank=True, null=True)
    is_correct = models.BooleanField(blank=True, null=True)
    points_awarded = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    needs_manual_grading = models.BooleanField(default=False)
    graded_at = models.DateTimeField(blank=True, null=True)
    graded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="graded_quiz_answers")

    class Meta:
        unique_together = ("attempt", "question")


class PasswordResetRequest(models.Model):
    """Track password reset requests that require admin approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_requests",
        limit_choices_to={"role__in": [User.Role.TEACHER, User.Role.STUDENT]},
    )
    personal_email = models.EmailField(help_text="Personal email where credentials will be sent")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_password_reset_requests",
        limit_choices_to={"role": User.Role.ADMIN},
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Password reset request for {self.user.email} - {self.status}"


class PushToken(models.Model):
    """Store FCM/APNs push notification tokens per user/device."""

    class DeviceType(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="push_tokens",
    )
    token = models.CharField(max_length=255, unique=True, help_text="FCM/APNs push token")
    device_type = models.CharField(max_length=20, choices=DeviceType.choices, default=DeviceType.ANDROID)
    device_name = models.CharField(max_length=100, blank=True, null=True, help_text="Optional device name for identification")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PushToken for {self.user.email} ({self.device_type})"


class ActivityReminder(models.Model):
    """Store reminder scheduling info for activities/quizzes."""

    class ReminderType(models.TextChoices):
        ACTIVITY = "activity", "Activity"
        QUIZ = "quiz", "Quiz"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activity_reminders",
    )
    reminder_type = models.CharField(max_length=20, choices=ReminderType.choices, default=ReminderType.ACTIVITY)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    quiz = models.ForeignKey(Quiz, null=True, blank=True, on_delete=models.CASCADE, related_name="reminders")
    reminder_datetime = models.DateTimeField(help_text="When the reminder notification should be sent")
    offset_minutes = models.PositiveIntegerField(default=0, help_text="Minutes before deadline (for display purposes)")
    notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reminder_datetime"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(reminder_type="activity", activity__isnull=False) |
                       models.Q(reminder_type="quiz", quiz__isnull=False),
                name="reminder_has_valid_target"
            )
        ]

    def __str__(self):
        target = self.activity if self.reminder_type == "activity" else self.quiz
        return f"Reminder for {target} - {self.user.email}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.reminder_type == "activity" and not self.activity:
            raise ValidationError("Activity reminder must have an activity")
        if self.reminder_type == "quiz" and not self.quiz:
            raise ValidationError("Quiz reminder must have a quiz")
