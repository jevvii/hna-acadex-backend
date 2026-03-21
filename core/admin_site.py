# hna-acadex-backend/core/admin_site.py
"""
Custom AdminSite that creates separate categories for better organization:
- Users: User management (appears first)
- Enrollment: Enrollment-related models
- Core: All other models
"""
from django.contrib.admin import AdminSite


class HnaAcadexAdminSite(AdminSite):
    """
    Custom admin site that organizes models into logical categories
    for easier navigation.
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

    def get_app_list(self, request):
        """
        Override to create virtual 'Users' and 'Enrollment' app groups
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

        # Create virtual Enrollment app
        enrollment_app = {
            'name': 'Enrollment',
            'app_label': 'enrollment',
            'app_url': '/admin/',
            'has_module_perms': True,
            'models': enrollment_models,
        }

        # Reorder: Users first, then Enrollment, then Core (and other apps)
        new_app_list = []

        # Add Users first if it has models
        if users_models:
            new_app_list.append(users_app)

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