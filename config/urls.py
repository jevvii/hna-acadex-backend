from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection
from django.db.utils import OperationalError
from django.shortcuts import render
from core.admin_site import admin_site
from core.teacher_portal.site import teacher_portal_site
from core.teacher_portal import admin  # Register teacher portal admin models
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

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


def healthz(request):
    """Basic health check endpoint for platform probes."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "ok"}, status=200)
    except OperationalError:
        return JsonResponse({"status": "degraded", "database": "error"}, status=503)


urlpatterns = [
    path("", portal_landing, name="portal_landing"),
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin_site.urls),
    path("teacher-portal/", teacher_portal_site.urls),
    path("api/", include("core.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG or not getattr(settings, "USE_CLOUDINARY_STORAGE", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
