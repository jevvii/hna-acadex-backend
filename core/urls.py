from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ActivityReminderViewSet,
    AttendanceOverviewView,
    AttendanceRecordBulkUpdateView,
    AttendanceSessionCreateView,
    AttendanceSessionDeleteView,
    ActivityMySubmissionView,
    ActivitySubmissionGradeView,
    ActivitySubmissionsForTeacherView,
    ActivitySubmitView,
    ActivityViewSet,
    AnnouncementViewSet,
    AssignmentGroupViewSet,
    AuthLoginView,
    AvatarUploadView,
    CalendarEventViewSet,
    ChangePasswordView,
    CourseFileViewSet,
    CourseSectionContentView,
    CourseSectionGradesView,
    CourseSectionGradesExportCSVView,
    DashboardStatsView,
    EnrollmentGradeOverrideView,
    ForgotPasswordRequestView,
    MeView,
    NotificationViewSet,
    PasswordResetRequestViewSet,
    ProfileViewSet,
    PushTokenViewSet,
    QuizAnswerGradeView,
    QuizGradingListView,
    QuizMyLatestAttemptView,
    QuizQuestionDetailView,
    QuizQuestionsView,
    QuizQuickCreateView,
    QuizSaveProgressView,
    QuizSubmitAttemptView,
    QuizTakeView,
    QuizViewSet,
    StudentCoursesView,
    WeeklyModuleViewSet,
    TeacherCoursesView,
    TodoItemViewSet,
)

router = DefaultRouter()
router.register(r"profiles", ProfileViewSet, basename="profiles")
router.register(r"todos", TodoItemViewSet, basename="todos")
router.register(r"calendar-events", CalendarEventViewSet, basename="calendar-events")
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"course-modules", WeeklyModuleViewSet, basename="course-modules")
router.register(r"assignment-groups", AssignmentGroupViewSet, basename="assignment-groups")
router.register(r"activities", ActivityViewSet, basename="activities")
router.register(r"course-files", CourseFileViewSet, basename="course-files")
router.register(r"announcements", AnnouncementViewSet, basename="announcements")
router.register(r"quizzes", QuizViewSet, basename="quizzes")
router.register(r"password-reset-requests", PasswordResetRequestViewSet, basename="password-reset-requests")
router.register(r"push-tokens", PushTokenViewSet, basename="push-tokens")
router.register(r"reminders", ActivityReminderViewSet, basename="reminders")

urlpatterns = [
    path("auth/login/", AuthLoginView.as_view(), name="auth-login"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/forgot-password/", ForgotPasswordRequestView.as_view(), name="auth-forgot-password"),
    path("profiles/me/avatar/", AvatarUploadView.as_view(), name="profile-avatar-upload"),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("courses/student/", StudentCoursesView.as_view(), name="student-courses"),
    path("courses/teacher/", TeacherCoursesView.as_view(), name="teacher-courses"),
    path("course-sections/<uuid:pk>/content/", CourseSectionContentView.as_view(), name="course-section-content"),
    path("course-sections/<uuid:pk>/grades/", CourseSectionGradesView.as_view(), name="course-section-grades"),
    path("course-sections/<uuid:pk>/grades/export/", CourseSectionGradesExportCSVView.as_view(), name="course-section-grades-export"),
    path(
        "course/<uuid:course_id>/section/<uuid:section_id>/grades/export/",
        CourseSectionGradesExportCSVView.as_view(),
        name="course-section-grades-export-alt",
    ),
    path("enrollments/<uuid:pk>/grade-override/", EnrollmentGradeOverrideView.as_view(), name="enrollment-grade-override"),
    path("course-sections/<uuid:pk>/attendance/", AttendanceOverviewView.as_view(), name="attendance-overview"),
    path("course-sections/<uuid:pk>/attendance/sessions/", AttendanceSessionCreateView.as_view(), name="attendance-session-create"),
    path("attendance/sessions/<uuid:pk>/", AttendanceSessionDeleteView.as_view(), name="attendance-session-delete"),
    path("attendance/sessions/<uuid:pk>/records/", AttendanceRecordBulkUpdateView.as_view(), name="attendance-records-update"),
    path("activities/<uuid:pk>/submit/", ActivitySubmitView.as_view(), name="activity-submit"),
    path("activities/<uuid:pk>/my-submission/", ActivityMySubmissionView.as_view(), name="activity-my-submission"),
    path("activities/<uuid:pk>/submissions/", ActivitySubmissionsForTeacherView.as_view(), name="activity-submissions"),
    path("activity-submissions/<uuid:pk>/grade/", ActivitySubmissionGradeView.as_view(), name="activity-submission-grade"),
    path("quizzes/<uuid:pk>/take/", QuizTakeView.as_view(), name="quiz-take"),
    path("quizzes/<uuid:pk>/submit-attempt/", QuizSubmitAttemptView.as_view(), name="quiz-submit-attempt"),
    path("quizzes/<uuid:pk>/save-progress/", QuizSaveProgressView.as_view(), name="quiz-save-progress"),
    path("quizzes/<uuid:pk>/my-latest-attempt/", QuizMyLatestAttemptView.as_view(), name="quiz-my-latest-attempt"),
    path("quizzes/<uuid:pk>/grading/", QuizGradingListView.as_view(), name="quiz-grading-list"),
    path("quiz-answers/<uuid:pk>/grade/", QuizAnswerGradeView.as_view(), name="quiz-answer-grade"),
    path("quizzes/quick-create/", QuizQuickCreateView.as_view(), name="quiz-quick-create"),
    path("quizzes/<uuid:pk>/questions/", QuizQuestionsView.as_view(), name="quiz-questions"),
    path("quiz-questions/<uuid:pk>/", QuizQuestionDetailView.as_view(), name="quiz-question-detail"),
    path("", include(router.urls)),
]
