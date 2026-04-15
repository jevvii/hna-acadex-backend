# Core views package - modular structure for better maintainability
# This package splits the monolithic views.py into organized modules

from .auth import (
    AuthLoginView,
    AuthLogoutView,
    MeView,
    ChangePasswordView,
    ForgotPasswordRequestView,
    ProfileViewSet,
    AvatarUploadView,
)

from .admin_views import (
    DashboardStatsView,
    PasswordResetRequestViewSet,
)

from .misc_views import (
    TodoItemViewSet,
    CalendarEventViewSet,
    WeeklyModuleViewSet,
    AssignmentGroupViewSet,
    CourseFileViewSet,
    AnnouncementViewSet,
    TeacherCourseSectionScopedModelViewSet,
    PushTokenViewSet,
    ActivityReminderViewSet,
    ActivityViewSet,
    QuizViewSet,
)

from .courses import (
    StudentCoursesView,
    TeacherCoursesView,
    CourseSectionDetailView,
    CourseSectionContentView,
)

from .attendance import (
    AttendanceOverviewView,
    AttendanceSessionCreateView,
    AttendanceSessionDeleteView,
    AttendanceRecordBulkUpdateView,
)

from .grades import (
    CourseSectionGradesView,
    CourseSectionGradebookView,
    CourseSectionGradesExportCSVView,
    EnrollmentGradeOverrideView,
    GradingPeriodListView,
    GradeWeightConfigView,
    StudentGradesView,
    AdvisoryGradesView,
    AdvisorySubjectReminderView,
    SubjectGradesView,
    GradeEntryCreateView,
    GradeEntryUpdateView,
    GradeEntryPublishView,
    BulkPublishGradesView,
    BulkPublishFinalGradesView,
    BulkTakeBackFinalGradesView,
    ComputeFinalGradeView,
    GradeSubmissionSubmitView,
    GradeSubmissionTakeBackView,
    ReportCardPublishView,
    ReportCardUnpublishView,
    AdviserOverrideView,
    StudentReportCardView,
)

from .activities import (
    ActivitySubmitView,
    ActivityMySubmissionView,
    ActivitySubmissionsForTeacherView,
    ActivitySubmissionGradeView,
    ActivityStudentGradeView,
    ActivityCommentsByActivityView,
    ActivityCommentViewSet,
)

from .quizzes import (
    QuizTakeView,
    QuizSubmitAttemptView,
    QuizSaveProgressView,
    QuizMyLatestAttemptView,
    QuizGradingListView,
    QuizAnswerGradeView,
    QuizQuestionsView,
    QuizQuestionDetailView,
    QuizQuestionsBulkView,
    QuizQuickCreateView,
)

from .notifications import (
    NotificationViewSet,
)

# Expose all public views
__all__ = [
    # Auth views
    'AuthLoginView',
    'AuthLogoutView',
    'MeView',
    'ChangePasswordView',
    'ForgotPasswordRequestView',
    'ProfileViewSet',
    'AvatarUploadView',
    # Admin views
    'DashboardStatsView',
    'PasswordResetRequestViewSet',
    # Misc views
    'TodoItemViewSet',
    'CalendarEventViewSet',
    'WeeklyModuleViewSet',
    'AssignmentGroupViewSet',
    'CourseFileViewSet',
    'AnnouncementViewSet',
    'TeacherCourseSectionScopedModelViewSet',
    'PushTokenViewSet',
    'ActivityReminderViewSet',
    'ActivityViewSet',
    'QuizViewSet',
    # Course views
    'StudentCoursesView',
    'TeacherCoursesView',
    'CourseSectionDetailView',
    'CourseSectionContentView',
    # Attendance views
    'AttendanceOverviewView',
    'AttendanceSessionCreateView',
    'AttendanceSessionDeleteView',
    'AttendanceRecordBulkUpdateView',
    # Grade views
    'CourseSectionGradesView',
    'CourseSectionGradebookView',
    'CourseSectionGradesExportCSVView',
    'EnrollmentGradeOverrideView',
    'GradingPeriodListView',
    'GradeWeightConfigView',
    'StudentGradesView',
    'AdvisoryGradesView',
    'AdvisorySubjectReminderView',
    'SubjectGradesView',
    'GradeEntryCreateView',
    'GradeEntryUpdateView',
    'GradeEntryPublishView',
    'BulkPublishGradesView',
    'BulkPublishFinalGradesView',
    'BulkTakeBackFinalGradesView',
    'ComputeFinalGradeView',
    'GradeSubmissionSubmitView',
    'GradeSubmissionTakeBackView',
    'ReportCardPublishView',
    'ReportCardUnpublishView',
    'AdviserOverrideView',
    'StudentReportCardView',
    # Activity views
    'ActivitySubmitView',
    'ActivityMySubmissionView',
    'ActivitySubmissionsForTeacherView',
    'ActivitySubmissionGradeView',
    'ActivityStudentGradeView',
    'ActivityCommentsByActivityView',
    'ActivityCommentViewSet',
    # Quiz views
    'QuizTakeView',
    'QuizSubmitAttemptView',
    'QuizSaveProgressView',
    'QuizMyLatestAttemptView',
    'QuizGradingListView',
    'QuizAnswerGradeView',
    'QuizQuestionsView',
    'QuizQuestionDetailView',
    'QuizQuestionsBulkView',
    'QuizQuickCreateView',
    # Notification views
    'NotificationViewSet',
]
