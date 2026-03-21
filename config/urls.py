from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from core.admin_site import admin_site

urlpatterns = [
    path("admin/", admin_site.urls),
    path("api/", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
