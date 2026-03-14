# hna-acadex-backend/core/tasks.py
"""
Celery tasks for background processing.

This module contains Celery tasks for processing reminders and other
background operations.
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(name="core.tasks.process_reminders")
def process_reminders():
    """
    Process pending activity reminders and send push notifications.

    This task should be run periodically (every minute) via Celery Beat.
    It finds all pending reminders where:
    - reminder_datetime <= now
    - notification_sent = False

    For each reminder:
    - Send push notification to user's devices
    - Mark as sent
    """
    from .models import ActivityReminder, PushToken
    from .push_notifications import PushNotificationService

    now = timezone.now()

    # Get all pending reminders
    pending_reminders = ActivityReminder.objects.filter(
        reminder_datetime__lte=now,
        notification_sent=False,
    ).select_related('user', 'activity', 'quiz')

    if not pending_reminders.exists():
        logger.debug("No pending reminders to process")
        return

    processed_count = 0
    error_count = 0

    for reminder in pending_reminders:
        try:
            user = reminder.user

            # Get activity/quiz details
            activity_id = None
            quiz_id = None
            course_section_id = None
            title = None
            body = None

            if reminder.reminder_type == "activity" and reminder.activity:
                activity_id = str(reminder.activity.id)
                course_section_id = str(reminder.activity.course_section_id)
                title = f"Assignment Reminder: {reminder.activity.title}"
                body = f"Don't forget to complete '{reminder.activity.title}'!"
            elif reminder.reminder_type == "quiz" and reminder.quiz:
                quiz_id = str(reminder.quiz.id)
                course_section_id = str(reminder.quiz.course_section_id)
                title = f"Quiz Reminder: {reminder.quiz.title}"
                body = f"Don't forget to take '{reminder.quiz.title}'!"

            # Send notification
            success = PushNotificationService.send_reminder_notification(
                user=user,
                reminder_type=reminder.reminder_type,
                activity_id=activity_id,
                quiz_id=quiz_id,
                course_section_id=course_section_id,
                title=title,
                body=body,
            )

            if success:
                reminder.notification_sent = True
                reminder.save(update_fields=['notification_sent'])
                processed_count += 1
                logger.info(f"Processed reminder {reminder.id} for user {user.id}")
            else:
                # Mark as sent anyway to prevent retries
                reminder.notification_sent = True
                reminder.save(update_fields=['notification_sent'])
                logger.warning(f"No active push tokens for reminder {reminder.id}")

        except Exception as e:
            logger.error(f"Error processing reminder {reminder.id}: {e}")
            error_count += 1

    logger.info(f"Processed {processed_count} reminders, {error_count} errors")


@shared_task(name="core.tasks.cleanup_inactive_push_tokens")
def cleanup_inactive_push_tokens():
    """
    Remove old inactive push tokens from the database.

    This task should be run periodically (daily) to clean up tokens
    that are no longer valid or have been deactivated.
    """
    from .models import PushToken

    # Remove push tokens that have been inactive for more than 90 days
    cutoff_date = timezone.now() - timedelta(days=90)

    deleted_count, _ = PushToken.objects.filter(
        is_active=False,
        updated_at__lt=cutoff_date
    ).delete()

    if deleted_count:
        logger.info(f"Cleaned up {deleted_count} inactive push tokens")


@shared_task(name="core.tasks.send_notification_for_course_section")
def send_notification_for_course_section(
    course_section_id: str,
    notif_type: str,
    title: str,
    body: str,
    activity_id: str = None,
    quiz_id: str = None,
    announcement_id: str = None,
):
    """
    Send push notification to all students enrolled in a course section.

    This is a background task version of the notification helper
    for use when notifications need to be sent asynchronously.

    Args:
        course_section_id: UUID of the course section
        notif_type: Notification type (new_activity, new_quiz, etc.)
        title: Notification title
        body: Notification body
        activity_id: Optional activity UUID
        quiz_id: Optional quiz UUID
        announcement_id: Optional announcement UUID
    """
    from .models import CourseSection, Enrollment, User, PushToken
    from .push_notifications import PushNotificationService

    try:
        course_section = CourseSection.objects.filter(id=course_section_id).first()
        if not course_section:
            logger.warning(f"Course section not found: {course_section_id}")
            return

        # Get all active students enrolled in this course section
        student_ids = list(
            Enrollment.objects.filter(
                course_section=course_section,
                is_active=True,
                student__status=User.Status.ACTIVE,
            )
            .values_list("student_id", flat=True)
            .distinct()
        )

        if not student_ids:
            logger.debug(f"No active students enrolled in course section {course_section_id}")
            return

        # Get all active push tokens for these students
        push_tokens = list(
            PushToken.objects.filter(
                user_id__in=student_ids,
                is_active=True,
            ).values_list('token', flat=True)
        )

        if not push_tokens:
            logger.debug(f"No active push tokens for students in course section {course_section_id}")
            return

        # Build data payload
        data = {
            "type": notif_type,
            "course_section_id": str(course_section_id),
        }

        if activity_id:
            data["activity_id"] = str(activity_id)

        if quiz_id:
            data["quiz_id"] = str(quiz_id)

        if announcement_id:
            data["announcement_id"] = str(announcement_id)

        # Send multicast notification
        success_count, failed_tokens = PushNotificationService.send_multicast_notification(
            tokens=push_tokens,
            title=title,
            body=body,
            data=data,
        )

        # Deactivate failed tokens
        if failed_tokens:
            PushToken.objects.filter(token__in=failed_tokens).update(is_active=False)
            logger.info(f"Deactivated {len(failed_tokens)} invalid push tokens")

        logger.info(f"Sent notification to {success_count} devices for course section {course_section_id}")

    except Exception as e:
        logger.error(f"Error sending notification for course section {course_section_id}: {e}")


@shared_task(name="core.tasks.send_notification_to_users")
def send_notification_to_users(
    user_ids: list,
    title: str,
    body: str,
    data: dict = None,
):
    """
    Send push notification to specific users.

    Args:
        user_ids: List of user UUIDs to notify
        title: Notification title
        body: Notification body
        data: Optional data payload
    """
    from .push_notifications import send_push_notification_to_users

    try:
        count = send_push_notification_to_users(
            user_ids=user_ids,
            title=title,
            body=body,
            data=data or {},
        )
        logger.info(f"Sent notification to {count} devices for {len(user_ids)} users")
    except Exception as e:
        logger.error(f"Error sending notification to users: {e}")