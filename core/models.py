# hna-acadex-backend/core/models.py
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
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
    # Name fields (separate for flexibility)
    first_name = models.CharField(max_length=100, help_text="First name (e.g., 'Juan')")
    last_name = models.CharField(max_length=100, help_text="Last name / Surname (e.g., 'Dela Cruz')")
    middle_name = models.CharField(max_length=100, blank=True, null=True, help_text="Middle name or initial (optional)")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    avatar = models.FileField(upload_to="avatars/", blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)
    grade_level = models.CharField(max_length=20, choices=GradeLevel.choices, blank=True, null=True)
    strand = models.CharField(max_length=10, choices=Strand.choices, default=Strand.NONE)
    section = models.CharField(max_length=100, blank=True, null=True)
    is_irregular = models.BooleanField(
        default=False,
        help_text="Mark this student as irregular — can be enrolled across sections by their advisory teacher"
    )
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    student_id = models.CharField(max_length=50, blank=True, null=True)
    theme = models.CharField(max_length=20, default="system")
    requires_setup = models.BooleanField(default=True, help_text="User must complete first-time setup (photo + password)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["status"]),
            models.Index(fields=["student_id"]),
            models.Index(fields=["employee_id"]),
            models.Index(fields=["role", "status"]),  # Compound index for role-based filtering
        ]

    @property
    def full_name(self) -> str:
        """Return the full name in 'LAST, FIRST, MIDDLE' format for backward compatibility."""
        if self.middle_name:
            return f"{self.last_name}, {self.first_name}, {self.middle_name}"
        return f"{self.last_name}, {self.first_name}"

    def get_full_name(self) -> str:
        """Return the full name in display format 'First Middle Last'."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.email})"


class IDCounter(models.Model):
    """Track sequential IDs per year and type.

    This model ensures unique and sequential ID generation for students
    and teachers. Each year gets a fresh sequence starting from 0001.

    Format: {prefix}{year}{sequential:04d}
    Example: 120240001 (first student of 2024)
    """

    class Type(models.TextChoices):
        STUDENT = "student", "Student"
        TEACHER = "teacher", "Teacher"

    year = models.IntegerField(help_text="The year for this ID sequence")
    id_type = models.CharField(max_length=10, choices=Type.choices, help_text="Student or Teacher ID type")
    prefix = models.IntegerField(default=1, help_text="Prefix number (1, 2, 3... for overflow handling)")
    sequential = models.IntegerField(default=0, help_text="Sequential number (0001-9999)")

    class Meta:
        unique_together = ('year', 'id_type')
        verbose_name = "ID Counter"
        verbose_name_plural = "ID Counters"

    def __str__(self):
        return f"{self.id_type} IDs for {self.year}: prefix={self.prefix}, seq={self.sequential}"


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        verbose_name="Section Name",
        help_text="The class section identifier (e.g., 'ICT-A', 'STEM-B1')"
    )
    grade_level = models.CharField(
        max_length=20,
        choices=User.GradeLevel.choices,
        verbose_name="Grade Level",
        help_text="The grade level this section belongs to"
    )
    strand = models.CharField(
        max_length=10,
        choices=User.Strand.choices,
        default=User.Strand.NONE,
        verbose_name="Strand/Track",
        help_text="Academic strand for senior high school (e.g., ICT, STEM, ABM)"
    )
    school_year = models.CharField(
        max_length=20,
        verbose_name="School Year",
        help_text="Academic year (e.g., '2024-2025')"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Class Section"
        verbose_name_plural = "Class Sections"

    def __str__(self):
        return f"{self.name} ({self.school_year})"


class Course(models.Model):
    class SubjectCategory(models.TextChoices):
        LANGUAGES_AP_ESP = "languages_ap_esp", "Languages, AP, ESP"
        SCIENCE_MATH = "science_math", "Science and Math"
        MAPEH_EPP_TLE = "mapeh_epp_tle", "MAPEH, EPP, TLE"
        SHS_CORE = "shs_core", "SHS Core Subject"
        SHS_APPLIED = "shs_applied", "SHS Applied Subject"
        SHS_SPECIALIZED = "shs_specialized", "SHS Specialized Subject"
        SHS_TVL = "shs_tvl", "SHS TVL Track"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=50,
        verbose_name="Course Code",
        help_text="Unique identifier code (e.g., 'CP102', 'MATH101')"
    )
    title = models.CharField(
        max_length=255,
        verbose_name="Course Title",
        help_text="Full name of the course (e.g., 'Introduction to Programming')"
    )
    description = models.TextField(blank=True, null=True)
    cover_image_url = models.URLField(blank=True, null=True)
    color_overlay = models.CharField(max_length=20, blank=True, null=True)
    grade_level = models.CharField(max_length=20, choices=User.GradeLevel.choices, blank=True, null=True)
    strand = models.CharField(max_length=10, choices=User.Strand.choices, blank=True, null=True)
    category = models.CharField(
        max_length=30,
        choices=SubjectCategory.choices,
        null=True,
        blank=True,
        verbose_name="Subject Category",
        help_text="Subject classification for DepEd grade weight defaults",
    )
    school_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20, blank=True, null=True)
    num_weeks = models.PositiveIntegerField(default=18)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return f"{self.code} - {self.title}"


class CourseSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="course_sections",
        verbose_name="Subject",
        help_text="Select the subject to be taught"
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="course_sections",
        verbose_name="Class Section",
        help_text="Select the class section that will take this subject"
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_course_sections",
        limit_choices_to={"role": User.Role.TEACHER},
        verbose_name="Teacher",
        help_text="Assign a teacher to teach this subject to this class section"
    )
    school_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("course", "section", "school_year", "semester")
        verbose_name = "Class Offering"
        verbose_name_plural = "Class Offerings"
        indexes = [
            models.Index(fields=["course"]),
            models.Index(fields=["teacher"]),
            models.Index(fields=["course", "teacher"]),  # Compound index for teacher course listings
        ]

    def __str__(self):
        return f"{self.course.code}@{self.section.name}"


class Enrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": User.Role.STUDENT},
        verbose_name="Student",
        help_text="Select a student to enroll"
    )
    course_section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="Class Offering",
        help_text="Select the class offering to enroll the student in"
    )
    final_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    manual_final_grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # DEPRECATED: Use SectionReportCard.is_published instead.
    # Kept for React Native app backward compatibility.
    is_final_published = models.BooleanField(
        default=False,
        help_text="Whether the final grade is visible to students"
    )
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course_section")
        verbose_name = "Student Enrollment"
        verbose_name_plural = "Student Enrollments"


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

    class ComponentType(models.TextChoices):
        WRITTEN_WORKS = "written_works", "Written Works"
        PERFORMANCE_TASK = "performance_task", "Performance Task"
        QUARTERLY_ASSESSMENT = "quarterly_assessment", "Quarterly Assessment"

    class ExamType(models.TextChoices):
        MONTHLY = "monthly", "Monthly Exam"
        QUARTERLY = "quarterly", "Quarterly Exam"

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
    allow_late_submissions = models.BooleanField(default=True)
    allowed_file_types = models.JSONField(blank=True, null=True)
    support_file_url = models.URLField(blank=True, null=True)
    attempt_limit = models.PositiveIntegerField(default=1)
    score_selection_policy = models.CharField(
        max_length=20,
        choices=ScorePolicy.choices,
        default=ScorePolicy.HIGHEST,
    )
    component_type = models.CharField(
        max_length=25,
        choices=ComponentType.choices,
        null=True,
        blank=True,
        verbose_name="Component Type",
        help_text="DepEd grade component: Written Works, Performance Task, or Quarterly Assessment",
    )
    is_exam = models.BooleanField(
        default=False,
        verbose_name="Is Exam",
        help_text="Whether this activity is an exam (Monthly or Quarterly)",
    )
    exam_type = models.CharField(
        max_length=10,
        choices=ExamType.choices,
        null=True,
        blank=True,
        verbose_name="Exam Type",
        help_text="Type of exam: Monthly (counts as Written Works) or Quarterly (counts as Quarterly Assessment)",
    )
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.is_exam and not self.exam_type:
            raise ValidationError(
                {"exam_type": "exam_type must be set when is_exam is True."}
            )
        if self.is_exam and self.exam_type == "monthly":
            self.component_type = self.ComponentType.WRITTEN_WORKS
        elif self.is_exam and self.exam_type == "quarterly":
            self.component_type = self.ComponentType.QUARTERLY_ASSESSMENT

    class Meta:
        indexes = [
            models.Index(fields=["course_section"]),
            models.Index(fields=["deadline"]),
        ]


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
    file_url = models.TextField()
    preview_file_url = models.TextField(blank=True, null=True)
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
        ordering = ["meeting__date", "student__last_name", "student__first_name"]


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
        indexes = [
            models.Index(fields=["activity"]),
            models.Index(fields=["student"]),
            models.Index(fields=["activity", "student"]),  # Compound index for grade queries
        ]


class QuizQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"
        MULTI_SELECT = "multi_select", "Multiple Select"
        TRUE_FALSE = "true_false", "True/False"
        IDENTIFICATION = "identification", "Identification"
        ESSAY = "essay", "Essay"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    question_type = models.CharField(max_length=30, choices=QuestionType.choices)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    sort_order = models.PositiveIntegerField(default=0)
    # Fields for identification type
    correct_answer = models.TextField(blank=True, default="")
    alternate_answers = models.JSONField(default=list, blank=True)
    case_sensitive = models.BooleanField(default=False)
    # Fields for essay type
    word_limit = models.PositiveIntegerField(null=True, blank=True)
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


class ActivityComment(models.Model):
    """Comments on activities by students and teachers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="comments")
    submission = models.ForeignKey(Submission, null=True, blank=True, on_delete=models.CASCADE, related_name="comments")
    thread_student = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_comment_threads",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    content = models.TextField(blank=True, null=True)
    file_urls = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author.full_name} on {self.activity.title}"


class CourseSectionGroup(models.Model):
    """Group multiple CourseSections together for batch enrollment.

    This allows admins to group up to 10 courses and enroll students
    to all courses in the group at once.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Descriptive name for this course group")
    description = models.TextField(blank=True, null=True, help_text="Optional description")
    course_sections = models.ManyToManyField(
        CourseSection,
        related_name="course_groups",
        limit_choices_to={"is_active": True},
        help_text="Select up to 10 course sections to include in this group"
    )
    school_year = models.CharField(max_length=20, help_text="Academic year (e.g., '2024-2025')")
    semester = models.CharField(max_length=20, blank=True, null=True, help_text="Semester (optional)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Enrollment Group"
        verbose_name_plural = "Enrollment Groups"

    def __str__(self):
        return f"{self.name} ({self.school_year})"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Course count validation is handled in admin form


class TeacherAdvisory(models.Model):
    """Records which Section a teacher is currently advising, scoped per school year.

    One teacher can advise at most one section per school year.
    One section can have at most one adviser per school year.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='advisory_assignments',
        limit_choices_to={'role': User.Role.TEACHER},
        verbose_name='Teacher'
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='advisory_assignments',
        verbose_name='Section'
    )
    school_year = models.CharField(
        max_length=20,
        help_text='Academic year e.g. 2024-2025',
        verbose_name='School Year'
    )
    is_active = models.BooleanField(default=True, verbose_name='Active')
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name='Assigned At')
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='advisory_assignments_made',
        limit_choices_to={'role': User.Role.ADMIN},
        verbose_name='Assigned By'
    )

    class Meta:
        unique_together = [
            ['teacher', 'school_year'],
            ['section', 'school_year'],
        ]
        verbose_name = 'Teacher Advisory'
        verbose_name_plural = 'Teacher Advisories'
        ordering = ['-school_year', 'section__name']

    def __str__(self):
        return f'{self.teacher.get_full_name()} → {self.section.name} ({self.school_year})'

    @property
    def advisory_section(self):
        """Convenience accessor for the advised section."""
        return self.section


class AuditLog(models.Model):
    """Audit log for sensitive operations."""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100)  # e.g., 'grade_change', 'password_reset'
    target_type = models.CharField(max_length=100, blank=True)  # Model name
    target_id = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    @classmethod
    def log(cls, request, action, target_type=None, target_id=None, details=None):
        """Create an audit log entry."""
        return cls.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


class GradingPeriod(models.Model):
    """Grading periods for academic terms.

    For Grades 7-10: Q1, Q2, Q3, Q4 (semester_group is null)
    For Grades 11-12: Q1+Q2 (semester_group=1), Q3+Q4 (semester_group=2)

    The semester_group groups quarters into semesters for Senior High.
    Q1+Q2 = 1st Semester, Q3+Q4 = 2nd Semester
    """

    class PeriodType(models.TextChoices):
        QUARTER = "quarter", "Quarter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_year = models.CharField(
        max_length=20,
        help_text="Academic year e.g., '2024-2025'"
    )
    period_type = models.CharField(
        max_length=10,
        choices=PeriodType.choices,
        default=PeriodType.QUARTER,
        help_text="Always 'quarter' - semesters are computed from quarter groups"
    )
    period_number = models.PositiveSmallIntegerField(
        help_text="1-4 for Q1, Q2, Q3, Q4"
    )
    semester_group = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="For Grades 11-12: 1 for Q1+Q2 (1st Sem), 2 for Q3+Q4 (2nd Sem). Null for Grades 7-10."
    )
    start_date = models.DateField(help_text="Start date of this grading period")
    end_date = models.DateField(help_text="End date of this grading period")
    is_current = models.BooleanField(
        default=False,
        help_text="Whether this is the current active grading period"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['school_year', 'semester_group', 'period_number']
        unique_together = ('school_year', 'semester_group', 'period_number')
        verbose_name = "Grading Period"
        verbose_name_plural = "Grading Periods"
        indexes = [
            models.Index(fields=['school_year']),
            models.Index(fields=['is_current']),
            models.Index(fields=['semester_group']),
        ]

    def __str__(self):
        return f"{self.school_year} - {self.label}"

    @property
    def label(self):
        """Return human-readable period label."""
        return f"Q{self.period_number}"

    @property
    def semester_label(self):
        """Return semester label if this quarter belongs to a semester group."""
        if self.semester_group == 1:
            return "1st Sem"
        elif self.semester_group == 2:
            return "2nd Sem"
        return None


class GradeEntry(models.Model):
    """Individual grade per student per subject per grading period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="grade_entries",
        verbose_name="Enrollment"
    )
    grading_period = models.ForeignKey(
        GradingPeriod,
        on_delete=models.CASCADE,
        related_name="grade_entries",
        verbose_name="Grading Period"
    )
    computed_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Auto-computed from activities/quizzes"
    )
    override_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Teacher-entered manual override"
    )
    # DEPRECATED: Use SectionReportCard.is_published instead.
    # Kept for React Native app backward compatibility.
    # Remove after RN app migrates to /api/students/me/report-card/
    is_published = models.BooleanField(
        default=False,
        help_text="Whether this grade is visible to students"
    )
    adviser_overridden = models.BooleanField(
        default=False,
        help_text="Whether an adviser has overridden this grade"
    )
    computed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['enrollment', 'grading_period__period_number']
        unique_together = ('enrollment', 'grading_period')
        verbose_name = "Grade Entry"
        verbose_name_plural = "Grade Entries"
        indexes = [
            models.Index(fields=['enrollment']),
            models.Index(fields=['grading_period']),
            models.Index(fields=['is_published']),
        ]

    def __str__(self):
        return f"{self.enrollment.student.full_name} - {self.grading_period.label} - {self.score}"

    @property
    def score(self):
        """Return override score if set, otherwise computed score."""
        return self.override_score if self.override_score is not None else self.computed_score


class GradeWeightConfig(models.Model):
    """Teacher-defined or DepEd-default grade weight configuration per course section."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.OneToOneField(
        CourseSection,
        on_delete=models.CASCADE,
        related_name="grade_weight_config",
        verbose_name="Course Section",
    )
    written_works = models.PositiveIntegerField(
        default=25,
        verbose_name="Written Works Weight (%)",
        help_text="Weight for Written Works component (quizzes + written activities + monthly exams)",
    )
    performance_tasks = models.PositiveIntegerField(
        default=50,
        verbose_name="Performance Tasks Weight (%)",
        help_text="Weight for Performance Tasks component (performance activities)",
    )
    quarterly_assessment = models.PositiveIntegerField(
        default=25,
        verbose_name="Quarterly Assessment Weight (%)",
        help_text="Weight for Quarterly Assessment component (quarterly exams)",
    )
    is_customized = models.BooleanField(
        default=False,
        help_text="Whether the teacher has customized the weights from DepEd defaults",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_weight_configs",
        verbose_name="Updated By",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Grade Weight Configuration"
        verbose_name_plural = "Grade Weight Configurations"

    def __str__(self):
        return f"{self.course_section} - WW:{self.written_works}% PT:{self.performance_tasks}% QA:{self.quarterly_assessment}%"

    def clean(self):
        from django.core.exceptions import ValidationError
        total = self.written_works + self.performance_tasks + self.quarterly_assessment
        if total != 100:
            raise ValidationError(
                f"Weights must sum to 100%. Current total: {total}%"
            )


# DEPRECATED: Superseded by GradeWeightConfig model.
# AssignmentWeight used activity/quiz/exam categories (70/20/10).
# GradeWeightConfig uses DepEd components (WW/PT/QA).
# Remove after confirming no active queries depend on this model.
class AssignmentWeight(models.Model):
    """Teacher-defined weight for activity/quiz/exam categories within a grading period."""

    class Category(models.TextChoices):
        ACTIVITY = "activity", "Activity"
        QUIZ = "quiz", "Quiz"
        EXAM = "exam", "Exam"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name="assignment_weights",
        verbose_name="Course Section"
    )
    grading_period = models.ForeignKey(
        GradingPeriod,
        on_delete=models.CASCADE,
        related_name="assignment_weights",
        verbose_name="Grading Period"
    )
    category = models.CharField(
        max_length=10,
        choices=Category.choices,
        help_text="Type of assignment: activity, quiz, or exam"
    )
    weight_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Weight as percentage (e.g., 30.00 for 30%)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['course_section', 'grading_period', 'category']
        unique_together = ('course_section', 'grading_period', 'category')
        verbose_name = "Assignment Weight"
        verbose_name_plural = "Assignment Weights"

    def __str__(self):
        return f"{self.course_section.course.code} - {self.grading_period.label} - {self.category}: {self.weight_percent}%"


class GradeSubmissionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    PUBLISHED = "published", "Published"


class GradeSubmission(models.Model):
    """Tracks submission status of grades for a course section in a grading period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name="grade_submissions",
        verbose_name="Course Section",
    )
    grading_period = models.ForeignKey(
        GradingPeriod,
        on_delete=models.CASCADE,
        related_name="grade_submissions",
        verbose_name="Grading Period",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_grades",
        verbose_name="Submitted By",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    taken_back_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=GradeSubmissionStatus.choices,
        default=GradeSubmissionStatus.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("course_section", "grading_period")
        ordering = ["-created_at"]
        verbose_name = "Grade Submission"
        verbose_name_plural = "Grade Submissions"

    def __str__(self):
        return f"{self.course_section} - {self.grading_period} - {self.status}"


class SectionReportCard(models.Model):
    """Tracks report card publication status for a section in a grading period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="report_cards",
        verbose_name="Section",
    )
    grading_period = models.ForeignKey(
        GradingPeriod,
        on_delete=models.CASCADE,
        related_name="report_cards",
        verbose_name="Grading Period",
    )
    published_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_report_cards",
        verbose_name="Published By",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("section", "grading_period")
        ordering = ["-created_at"]
        verbose_name = "Section Report Card"
        verbose_name_plural = "Section Report Cards"

    def __str__(self):
        status = "Published" if self.is_published else "Unpublished"
        return f"{self.section} - {self.grading_period} - {status}"


class AdviserOverrideLog(models.Model):
    """Audit log for adviser overrides on student grades."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade_entry = models.ForeignKey(
        GradeEntry,
        on_delete=models.CASCADE,
        related_name="override_logs",
        verbose_name="Grade Entry",
    )
    adviser = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="adviser_overrides",
        verbose_name="Adviser",
    )
    previous_score = models.DecimalField(max_digits=5, decimal_places=2)
    new_score = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Adviser Override Log"
        verbose_name_plural = "Adviser Override Logs"

    def __str__(self):
        return f"Override by {self.adviser}: {self.previous_score} -> {self.new_score}"
