# Teacher Portal Admin Site
"""
Custom AdminSite for the Teacher Portal.

This provides a separate admin interface for teachers to manage their
advisory sections. Teachers don't need is_staff=True - access is granted
based on their role being 'teacher' and is_active=True.
"""

from django.contrib.admin import AdminSite
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from .forms import TeacherAuthenticationForm


class TeacherPortalAdminSite(AdminSite):
    """
    Custom admin site for teachers.

    Teachers can access this portal without being staff members.
    They can only see and manage models related to their advisory section.
    """

    site_header = "HNA Acadex Teacher Portal"
    site_title = "Teacher Portal"
    index_title = "Advisory Dashboard"
    login_url = "/teacher-portal/login/"
    login_template = "teacher_portal/login.html"
    login_form = TeacherAuthenticationForm

    def has_permission(self, request):
        """
        Check if the user has permission to access the teacher portal.

        Allows access for:
        - Authenticated users with role='teacher' and is_active=True
        """
        return (
            request.user.is_authenticated and
            request.user.is_active and
            request.user.role == 'teacher'
        )

    def get_app_list(self, request):
        """
        Build a 4-group sidebar for the teacher's advisory.

        Groups:
        1. 'Advisory Dashboard': Link to index with enrollment list
        2. 'My Students': Student management (User model)
        3. 'My Curriculum': Course management (Course, CourseSectionGroup)
        4. 'SIS Import': Link to teacher SIS import index

        Returns empty list with redirect hint if teacher has no active TeacherAdvisory.
        """
        from core.models import TeacherAdvisory
        from django.urls import reverse

        # Return empty list for unauthenticated users
        if not request.user.is_authenticated:
            return []

        # Check if teacher has an active advisory assignment
        advisory = TeacherAdvisory.objects.filter(
            teacher=request.user,
            is_active=True
        ).select_related('section').first()

        if not advisory:
            # Return empty list - views should redirect to 'no advisory' page
            return [{
                'name': 'Setup',
                'app_label': 'setup',
                'app_url': '#',
                'has_module_perms': True,
                'models': [],
                'no_advisory': True,
            }]

        # Store advisory in request for use by views
        request.teacher_advisory = advisory

        # Get base app list from super()
        base_list = super().get_app_list(request)

        # Build custom app list with 4 groups
        app_list = []

        # Group 1: Advisory Dashboard (link to index)
        app_list.append({
            'name': 'Advisory Dashboard',
            'app_label': 'advisory_dashboard',
            'app_url': '/teacher-portal/',
            'has_module_perms': True,
            'models': [{
                'name': 'Student Enrollments',
                'object_name': 'Enrollment',
                'admin_url': '/teacher-portal/',
                'add_url': '/teacher-portal/core/enrollment/add/',
            }],
        })

        # Group 2: My Students (user model)
        for app in base_list:
            if app.get('app_label') == 'core':
                for model in app.get('models', []):
                    if model.get('object_name', '').lower() == 'user':
                        app_list.append({
                            'name': 'My Students',
                            'app_label': 'my_students',
                            'app_url': model.get('admin_url', '#'),
                            'has_module_perms': True,
                            'models': [model],
                        })
                        break

        # Group 3: My Curriculum (course, coursesectiongroup)
        curriculum_models = []
        for app in base_list:
            if app.get('app_label') == 'core':
                for model in app.get('models', []):
                    model_name = model.get('object_name', '').lower()
                    if model_name in ['course', 'coursesectiongroup']:
                        curriculum_models.append(model)

        if curriculum_models:
            app_list.append({
                'name': 'My Curriculum',
                'app_label': 'my_curriculum',
                'app_url': '#',
                'has_module_perms': True,
                'models': curriculum_models,
            })

        # Group 4: SIS Import
        app_list.append({
            'name': 'SIS Import',
            'app_label': 'sis_import',
            'app_url': reverse('teacher_portal:tp_sis_import_index'),
            'has_module_perms': True,
            'models': [],
        })

        return app_list

    def get_urls(self):
        """Add custom teacher portal URLs."""
        # Import admin to ensure models are registered before URL patterns are built
        from . import admin  # noqa: F401
        from . import views as teacher_portal_views

        urls = super().get_urls()

        # Teacher portal specific URLs (wrapped with admin_view for authentication)
        custom_urls = [
            path('', self.admin_view(teacher_portal_views.dashboard), name='index'),
            path('sis-import/', self.admin_view(teacher_portal_views.sis_import_index), name='tp_sis_import_index'),
            path('sis-import/users/', self.admin_view(teacher_portal_views.sis_import_users), name='tp_sis_import_users'),
            path('sis-import/enrollments/', self.admin_view(teacher_portal_views.sis_import_enrollments), name='tp_sis_import_enrollments'),
            path('sis-import/courses/', self.admin_view(teacher_portal_views.sis_import_courses), name='tp_sis_import_courses'),
            path('sis-import/course-sections/', self.admin_view(teacher_portal_views.sis_import_course_sections), name='tp_sis_import_course_sections'),
            # Template download URLs
            path('sis-import/template/users/', self.admin_view(teacher_portal_views.download_users_template), name='tp_sis_template_users'),
            path('sis-import/template/enrollments/', self.admin_view(teacher_portal_views.download_enrollments_template), name='tp_sis_template_enrollments'),
            path('sis-import/template/courses/', self.admin_view(teacher_portal_views.download_courses_template), name='tp_sis_template_courses'),
            path('sis-import/template/course-sections/', self.admin_view(teacher_portal_views.download_course_sections_template), name='tp_sis_template_course_sections'),
        ]

        return custom_urls + urls


# Create the singleton teacher portal admin site instance
teacher_portal_site = TeacherPortalAdminSite(name='teacher_portal')