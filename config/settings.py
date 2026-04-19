from pathlib import Path
import os
import sys
import ssl
from datetime import timedelta
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

BUILD_TIME_MANAGEMENT_COMMANDS = {"collectstatic", "migrate", "createsu"}
RUNNING_BUILD_MANAGEMENT_COMMAND = (
    len(sys.argv) > 1
    and Path(sys.argv[0]).name == "manage.py"
    and sys.argv[1] in BUILD_TIME_MANAGEMENT_COMMANDS
)
SKIP_PRODUCTION_ENV_VALIDATION = (
    os.getenv("SKIP_PRODUCTION_ENV_VALIDATION", "0") == "1"
    or RUNNING_BUILD_MANAGEMENT_COMMAND
)

# Security key - must be set via environment variable
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required")

if SECRET_KEY in ["dev-secret-key-change-this", "secret", "test", "your-secret-key-here-change-in-production"]:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be changed from default in production")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Security settings for production
if not DEBUG:
    # Render and other reverse proxies terminate TLS before forwarding to Django.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# CSRF trusted origins for local development and production
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8081",
    "http://localhost:8081",
]
# Add production origins from environment if provided
_prod_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if _prod_origins:
    CSRF_TRUSTED_ORIGINS.extend([origin.strip() for origin in _prod_origins.split(",") if origin.strip()])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_celery_beat",  # Required for Celery Beat database scheduler
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.teacher_portal.context_processors.teacher_advisory",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DEBUG and not SKIP_PRODUCTION_ENV_VALIDATION and not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL environment variable is required in production")

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
USE_CLOUDINARY_STORAGE = False

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Cloudinary Configuration (for media storage in production)
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", None)
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", None)
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", None)
# Auth token key for restricted delivery (found in Cloudinary Dashboard > Settings > Security)
CLOUDINARY_AUTH_TOKEN_KEY = os.getenv("CLOUDINARY_AUTH_TOKEN_KEY", None)

# Cloudinary Configuration for media storage
# Set CLOUDINARY_URL env var in format: cloudinary://api_key:api_secret@cloud_name
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", None)

# Parse CLOUDINARY_URL into individual vars when they aren't set explicitly
if CLOUDINARY_URL and not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
    try:
        _parsed = urlparse(CLOUDINARY_URL)
        CLOUDINARY_CLOUD_NAME = CLOUDINARY_CLOUD_NAME or _parsed.hostname
        CLOUDINARY_API_KEY = CLOUDINARY_API_KEY or _parsed.username
        CLOUDINARY_API_SECRET = CLOUDINARY_API_SECRET or _parsed.password
    except Exception:
        pass

USE_CLOUDINARY_STORAGE = bool(
    CLOUDINARY_URL or (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)
)

if USE_CLOUDINARY_STORAGE:
    if "cloudinary" not in INSTALLED_APPS:
        INSTALLED_APPS.append("cloudinary")
    if "cloudinary_storage" not in INSTALLED_APPS:
        INSTALLED_APPS.append("cloudinary_storage")

    import cloudinary
    if CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=CLOUDINARY_URL, secure=True)
    else:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )

    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
        "API_KEY": CLOUDINARY_API_KEY,
        "API_SECRET": CLOUDINARY_API_SECRET,
    }

    STORAGES["default"] = {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"}
    # Backward-compatible alias for packages that still read this setting.
    DEFAULT_FILE_STORAGE = STORAGES["default"]["BACKEND"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"

# Disable APPEND_SLASH to prevent POST redirect issues
# Our API endpoints already use trailing slashes in URL patterns
APPEND_SLASH = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Rate limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = "default"

# Email Configuration
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# Email Backend Type: 'brevo' (production) or 'smtp' (development)
# Set to 'smtp' in .env for local development with Gmail
EMAIL_BACKEND_TYPE = os.getenv("EMAIL_BACKEND_TYPE", "brevo").lower()

# Brevo API Configuration (alternative to SMTP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", None)

# Frontend URL for email links
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8081")

CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "0") == "1"
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
# Required for frontend credentials: 'include' to work
CORS_ALLOW_CREDENTIALS = True

# Production override: require explicit CORS configuration
if not DEBUG and not SKIP_PRODUCTION_ENV_VALIDATION and 'CORS_ALLOWED_ORIGINS' not in os.environ:
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS environment variable must be set in production")
if CORS_ALLOW_ALL_ORIGINS:
    if CORS_ALLOW_CREDENTIALS:
        raise ImproperlyConfigured("CORS_ALLOW_ALL_ORIGINS cannot be enabled when CORS_ALLOW_CREDENTIALS is True")
    if not DEBUG:
        raise ImproperlyConfigured("CORS_ALLOW_ALL_ORIGINS must be disabled in production")

# Ensure CSRF trusted origins stays aligned with browser origins used by web clients.
for origin in CORS_ALLOWED_ORIGINS:
    if origin.startswith(("http://", "https://")) and origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Auth lifetime tuning for persistent mobile sessions and session-scoped web cookies.
JWT_ACCESS_TOKEN_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15"))
JWT_REFRESH_TOKEN_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "180"))
AUTH_COOKIE_USE_SESSION = os.getenv("AUTH_COOKIE_USE_SESSION", "1") == "1"

# JWT Configuration for HttpOnly cookie-based authentication
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_TOKEN_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Cookie settings for frontend integration
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_REFRESH": "refresh_token",
    "AUTH_COOKIE_SECURE": not DEBUG,  # Secure in production, not in dev
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SAMESITE": "Lax",
    "AUTH_COOKIE_PATH": "/",
    "AUTH_COOKIE_USE_SESSION": AUTH_COOKIE_USE_SESSION,
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# SSL settings for Upstash Redis (rediss://)
if CELERY_BROKER_URL.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}
if CELERY_RESULT_BACKEND.startswith("rediss://"):
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}

# Celery Beat Configuration
CELERY_BEAT_SCHEDULE = {
    "process-reminders-every-minute": {
        "task": "core.tasks.process_reminders",
        "schedule": 60.0,  # Every minute
    },
    "cleanup-push-tokens-daily": {
        "task": "core.tasks.cleanup_inactive_push_tokens",
        "schedule": 86400.0,  # Every 24 hours
    },
}

# Firebase Configuration for Push Notifications
# Supports two methods:
# 1. FIREBASE_CREDENTIALS_JSON - JSON string of credentials (recommended for production)
# 2. FIREBASE_CREDENTIALS_PATH - Path to credentials file (for local development)
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", None)
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", None)

# Logging Configuration
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO")
CORE_LOG_LEVEL = os.getenv("CORE_LOG_LEVEL", "DEBUG" if DEBUG else "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
        },
        "core": {
            "handlers": ["console"],
            "level": CORE_LOG_LEVEL,
            "propagate": True,
        },
    },
}

# API Documentation Settings (drf-spectacular)
SPECTACULAR_SETTINGS = {
    "TITLE": "HNA Acadex API",
    "DESCRIPTION": "Learning Management System API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"bearerAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
}
