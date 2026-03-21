# hna-acadex-backend/core/admin_site.py
"""
Custom AdminSite that creates separate categories for better organization:
- Users: User management (appears first)
- SIS Import: Bulk import functionality
- Enrollment: Enrollment-related models
- Core: All other models
"""
from django.contrib.admin import AdminSite
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _


class HnaAcadexAdminSite(AdminSite):
    """
    Custom admin site that organizes models into logical categories
    for easier navigation and includes SIS Import functionality.
    """

    site_header = "HNA Acadex Administration"
    site_title = "HNA Acadex Admin"
    index_title = "Welcome to HNA Acadex Admin"

    # Models that belong to the "Users" category (lowercase object_name)
    USERS_MODELS = {
        'user',
    }

    # Models that belong to the "Enrollment" category (lowercase object_name)
    ENROLLMENT_MODELS = {
        'course',
        'section',
        'coursesection',
        'coursesectiongroup',
        'enrollment',
    }

    def get_urls(self):
        """Add SIS Import URLs to the admin site."""
        from django.urls import include
        from core.sis_import import views as sis_import_views

        # Get default admin URLs
        urls = super().get_urls()

        # Add SIS Import URLs
        sis_import_urls = [
            path('sis-import/', self.admin_view(sis_import_views.sis_import_index), name='sis_import_index'),
            path('sis-import/courses/', self.admin_view(sis_import_views.sis_import_courses), name='sis_import_courses'),
            path('sis-import/users/', self.admin_view(sis_import_views.sis_import_users), name='sis_import_users'),
            path('sis-import/sections/', self.admin_view(sis_import_views.sis_import_sections), name='sis_import_sections'),
            path('sis-import/enrollments/', self.admin_view(sis_import_views.sis_import_enrollments), name='sis_import_enrollments'),
            # Template download URLs
            path('sis-import/template/courses/', self.admin_view(sis_import_views.download_courses_template), name='sis_import_download_courses_template'),
            path('sis-import/template/users/', self.admin_view(sis_import_views.download_users_template), name='sis_import_download_users_template'),
            path('sis-import/template/sections/', self.admin_view(sis_import_views.download_sections_template), name='sis_import_download_sections_template'),
            path('sis-import/template/enrollments/', self.admin_view(sis_import_views.download_enrollments_template), name='sis_import_download_enrollments_template'),
        ]

        # Return SIS Import URLs first, then default URLs
        return sis_import_urls + urls

    def get_app_list(self, request):
        """
        Override to create virtual 'Users', 'SIS Import', and 'Enrollment' app groups
        and reorder apps for better organization.
        """
        app_list = super().get_app_list(request)

        # Find the Core app
        core_app = None
        for app in app_list:
            if app.get('app_label') == 'core':
                core_app = app
                break

        if core_app is None:
            return app_list

        # Split Core models into users, enrollment, and other categories
        users_models = []
        enrollment_models = []
        other_models = []

        for model in core_app.get('models', []):
            model_name = model.get('object_name', '').lower()
            if model_name in self.USERS_MODELS:
                users_models.append(model)
            elif model_name in self.ENROLLMENT_MODELS:
                enrollment_models.append(model)
            else:
                other_models.append(model)

        # Update Core app to only have non-users, non-enrollment models
        core_app['models'] = other_models

        # Create virtual Users app
        users_app = {
            'name': 'Users',
            'app_label': 'users',
            'app_url': '/admin/',
            'has_module_perms': True,
            'models': users_models,
        }

        # Create virtual SIS Import app (as a model-less app with a single link)
        sis_import_app = {
            'name': 'SIS Import',
            'app_label': 'sis_import',
            'app_url': reverse('admin:sis_import_index'),
            'has_module_perms': True,
            'models': [],  # No models, just a link to the import page
        }

        # Create virtual Enrollment app
        enrollment_app = {
            'name': 'Enrollment',
            'app_label': 'enrollment',
            'app_url': '/admin/',
            'has_module_perms': True,
            'models': enrollment_models,
        }

        # Reorder: Users first, then SIS Import, then Enrollment, then Core (and other apps)
        new_app_list = []

        # Add Users first if it has models
        if users_models:
            new_app_list.append(users_app)

        # Add SIS Import (always visible)
        new_app_list.append(sis_import_app)

        # Add Enrollment next if it has models
        if enrollment_models:
            new_app_list.append(enrollment_app)

        # Add remaining apps (Core will be after Enrollment now)
        for app in app_list:
            if app.get('app_label') == 'core':
                # Only add Core if it still has models
                if app.get('models'):
                    new_app_list.append(app)
            else:
                new_app_list.append(app)

        return new_app_list


# Create the singleton admin site instance
admin_site = HnaAcadexAdminSite(name='hna_acadex_admin')