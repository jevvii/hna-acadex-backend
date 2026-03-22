# Teacher Portal Context Processors
"""
Context processors for the Teacher Portal.

These add context variables to all teacher portal templates.
"""

from django.contrib.auth.models import AnonymousUser
from core.models import TeacherAdvisory


def teacher_advisory(request):
    """
    Add teacher_advisory to context for all teacher portal requests.

    Returns:
        dict: {'teacher_advisory': TeacherAdvisory or None}
    """
    # Guard against non-authenticated requests and non-teacher users
    if not hasattr(request, 'user') or isinstance(request.user, AnonymousUser):
        return {}

    if not request.user.is_authenticated:
        return {}

    if not hasattr(request.user, 'role') or request.user.role != 'teacher':
        return {}

    # Check if already cached on request
    if hasattr(request, 'teacher_advisory'):
        return {'teacher_advisory': request.teacher_advisory}

    # Look up active advisory assignment
    advisory = TeacherAdvisory.objects.filter(
        teacher=request.user,
        is_active=True
    ).select_related('section').first()

    return {'teacher_advisory': advisory}