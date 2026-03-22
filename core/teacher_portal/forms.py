# Teacher Portal Forms
"""
Custom forms for the Teacher Portal.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class TeacherAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form for the Teacher Portal.

    Allows login for users with role='teacher' and is_active=True,
    without requiring is_staff=True.
    """

    error_messages = {
        "invalid_login": _(
            "Please enter the correct %(username)s and password for a "
            "teacher account. Note that both fields may be case-sensitive."
        ),
        "inactive": _("This account is inactive."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'tp-form-input',
            'placeholder': 'teacher@hna.edu.ph',
            'autocomplete': 'email',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({
            'class': 'tp-form-input',
            'placeholder': '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022',
            'autocomplete': 'current-password',
        })

    def confirm_login_allowed(self, user):
        """
        Controls whether the given User may log in.

        This is overridden to allow teachers (role='teacher') to log in
        without requiring is_staff=True.
        """
        if not user.is_active:
            raise forms.ValidationError(
                self.error_messages["inactive"],
                code="inactive",
            )
        if not hasattr(user, 'role') or user.role != 'teacher':
            raise forms.ValidationError(
                _("This account is not authorized for the Teacher Portal. "
                  "Only teachers can log in here."),
                code="not_teacher",
            )