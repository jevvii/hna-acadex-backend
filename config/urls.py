from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.shortcuts import render
from core.admin_site import admin_site
from core.teacher_portal.site import teacher_portal_site
from core.teacher_portal import admin  # Register teacher portal admin models

# Import teacher portal admin to register models
import core.teacher_portal.admin  # noqa: F401


def portal_landing(request):
    """Landing page with links to admin and teacher portals."""
    from datetime import datetime
    context = {
        'admin_url': '/admin/',
        'teacher_portal_url': '/teacher-portal/',
        'current_year': datetime.now().year,
    }
    return render(request, 'portal_landing.html', context)


urlpatterns = [
    path("", portal_landing, name="portal_landing"),
    path("admin/", admin_site.urls),
    path("teacher-portal/", teacher_portal_site.urls),
    path("api/", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)