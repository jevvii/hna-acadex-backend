from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Import signal handlers.
        from . import signals  # noqa: F401
        # Register drf-spectacular schema extensions.
        from . import schema  # noqa: F401
