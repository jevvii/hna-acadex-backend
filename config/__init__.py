# config/__init__.py
"""Configuration package for HNA Acadex backend."""

# This will make sure the app is always imported when Django starts
# Celery is optional - only import if installed
try:
    from .celery import app as celery_app
    __all__ = ("celery_app",)
except ImportError:
    # Celery not installed, skip
    pass