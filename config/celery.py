# config/celery.py
"""Celery configuration for HNA Acadex backend."""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("hna_acadex")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Set up periodic tasks from Django settings."""
    # Import tasks to ensure they are registered
    from core import tasks  # noqa: F401

    # Add periodic tasks from settings
    for name, task_config in getattr(settings, "CELERY_BEAT_SCHEDULE", {}).items():
        sender.add_periodic_task(
            task_config.get("schedule", 60.0),
            task_config["task"],
            name=name,
        )