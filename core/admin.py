from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import (
    Activity,
    Announcement,
    AssignmentGroup,
    AttendanceRecord,
    CalendarEvent,
    Course,
    CourseFile,
    CourseSection,
    Enrollment,
    Notification,
    MeetingSession,
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


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = (
        "email",
        "full_name",
        "role",
        "status",
        "is_staff",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "status", "is_staff", "is_superuser", "is_active")
    ordering = ("-created_at",)
    search_fields = ("email", "full_name", "employee_id", "student_id")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "full_name",
                    "avatar",
                    "avatar_url",
                    "role",
                    "status",
                    "grade_level",
                    "strand",
                    "section",
                    "employee_id",
                    "student_id",
                    "theme",
                )
            },
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "role",
                    "status",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at", "date_joined", "last_login")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "grade_level", "strand", "school_year", "is_active")
    list_filter = ("grade_level", "strand", "school_year", "is_active")
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "school_year", "semester", "is_active")
    list_filter = ("school_year", "semester", "is_active")
    search_fields = ("code", "title")


@admin.register(CourseSection)
class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ("course", "section", "teacher", "school_year", "semester", "is_active")
    list_filter = ("school_year", "semester", "is_active")
    search_fields = ("course__code", "course__title", "section__name", "teacher__full_name")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course_section", "final_grade", "is_active", "enrolled_at")
    list_filter = ("is_active", "course_section__school_year")
    search_fields = ("student__full_name", "student__email")


@admin.register(WeeklyModule)
class WeeklyModuleAdmin(admin.ModelAdmin):
    list_display = ("course_section", "week_number", "title", "is_exam_week", "is_published")
    list_filter = ("is_exam_week", "is_published")


@admin.register(AssignmentGroup)
class AssignmentGroupAdmin(admin.ModelAdmin):
    list_display = ("course_section", "name", "weight_percent", "is_active", "created_at")
    list_filter = ("is_active", "course_section")
    search_fields = ("name", "course_section__course__title", "course_section__section__name")


@admin.register(MeetingSession)
class MeetingSessionAdmin(admin.ModelAdmin):
    list_display = ("course_section", "date", "title", "created_by", "created_at")
    list_filter = ("date", "course_section")
    search_fields = ("title", "course_section__course__title", "course_section__section__name")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("meeting", "student", "status", "marked_by", "updated_at")
    list_filter = ("status", "meeting__course_section")
    search_fields = ("student__full_name", "student__email", "meeting__title")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "points", "deadline", "is_published")
    list_filter = ("is_published",)


@admin.register(CourseFile)
class CourseFileAdmin(admin.ModelAdmin):
    list_display = ("file_name", "course_section", "category", "is_visible", "created_at")
    list_filter = ("category", "is_visible")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "attempt_limit", "is_published", "created_at")
    list_filter = ("is_published",)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ("quiz", "question_type", "question_text", "points", "sort_order")
    list_filter = ("question_type",)
    search_fields = ("question_text", "quiz__title")


@admin.register(QuizChoice)
class QuizChoiceAdmin(admin.ModelAdmin):
    list_display = ("question", "choice_text", "is_correct", "sort_order")
    list_filter = ("is_correct",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("quiz", "student", "attempt_number", "score", "max_score", "is_submitted", "pending_manual_grading", "submitted_at")
    list_filter = ("is_submitted", "pending_manual_grading")
    search_fields = ("quiz__title", "student__full_name", "student__email")


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "points_awarded", "needs_manual_grading", "graded_at")
    list_filter = ("needs_manual_grading", "is_correct")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("activity", "student", "status", "score", "submitted_at", "graded_at")
    list_filter = ("status",)
    search_fields = ("activity__title", "student__full_name", "student__email")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "school_wide", "audience", "is_published", "created_at")
    list_filter = ("school_wide", "audience", "is_published")


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "event_type", "start_at", "all_day", "is_personal")
    list_filter = ("event_type", "all_day", "is_personal")


@admin.register(TodoItem)
class TodoItemAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "due_at", "is_done", "created_at")
    list_filter = ("is_done",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read")
