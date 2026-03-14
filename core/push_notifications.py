# hna-acadex-backend/core/push_notifications.py
"""
Push notification service supporting both Expo and FCM/APNs tokens.

This module provides functionality to send push notifications to users'
devices. It automatically detects token type and routes accordingly:
- Expo tokens (ExponentPushToken[...]) -> Expo Push Service
- Native FCM/APNs tokens -> Firebase Cloud Messaging
"""

import logging
import os
import requests
from typing import Optional, List, Tuple
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Firebase Admin SDK instance
_firebase_app = None

# Expo Push Notification API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def is_expo_token(token: str) -> bool:
    """
    Check if a token is an Expo push token.

    Expo tokens have the format: ExponentPushToken[xxxxx]
    Native FCM tokens are long alphanumeric strings without this prefix.
    """
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


def separate_tokens_by_type(tokens: List[str]) -> Tuple[List[str], List[str]]:
    """
    Separate tokens into Expo tokens and native FCM tokens.

    Returns:
        Tuple of (expo_tokens, fcm_tokens)
    """
    expo_tokens = []
    fcm_tokens = []

    for token in tokens:
        if is_expo_token(token):
            expo_tokens.append(token)
        else:
            fcm_tokens.append(token)

    return expo_tokens, fcm_tokens


def send_expo_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Tuple[int, List[str]]:
    """
    Send push notifications via Expo's push service.

    Args:
        tokens: List of Expo push tokens
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        Tuple of (successful_count, failed_tokens)
    """
    if not tokens:
        return (0, [])

    # Build messages for each token
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }
        for token in tokens
    ]

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        success_count = 0
        failed_tokens = []

        # Process results
        data_list = result.get("data", [])
        for idx, ticket in enumerate(data_list):
            if ticket.get("status") == "ok":
                success_count += 1
            else:
                failed_tokens.append(tokens[idx])
                error_message = ticket.get("message", "Unknown error")
                error_details = ticket.get("details", {})

                # Log specific error types
                if "DeviceNotRegistered" in str(error_details):
                    logger.warning(f"Device not registered: {tokens[idx][:20]}...")
                elif "InvalidCredentials" in str(error_details):
                    logger.warning(f"Invalid credentials for token: {tokens[idx][:20]}...")
                else:
                    logger.warning(f"Expo push failed for {tokens[idx][:20]}...: {error_message}")

        logger.info(f"Expo push: {success_count} successful, {len(failed_tokens)} failed")
        return (success_count, failed_tokens)

    except requests.RequestException as e:
        logger.error(f"Failed to send Expo push notification: {e}")
        return (0, tokens)


def get_firebase_app():
    """
    Get or initialize the Firebase Admin SDK app.

    Returns None if Firebase is not configured.
    """
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Check if already initialized
        if firebase_admin._apps:
            _firebase_app = list(firebase_admin._apps.values())[0]
            return _firebase_app

        # Get credentials path from settings
        credentials_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)

        if not credentials_path:
            # Check environment variable
            credentials_path = os.environ.get('FIREBASE_CREDENTIALS_PATH')

        if not credentials_path:
            logger.info("Firebase credentials not configured. Push notifications disabled.")
            return None

        if not os.path.exists(credentials_path):
            logger.warning(f"Firebase credentials file not found: {credentials_path}")
            return None

        cred = credentials.Certificate(credentials_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        return _firebase_app

    except ImportError:
        logger.warning("firebase-admin package not installed. Push notifications disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None


def send_push_notification_to_user(
    user_id,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """
    Send a push notification to a specific user's devices.

    Args:
        user_id: The user ID to send notification to
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        True if sent to at least one device, False otherwise
    """
    from .models import PushToken

    # Get all active push tokens for the user
    push_tokens = list(
        PushToken.objects.filter(user_id=user_id, is_active=True).values_list('token', flat=True)
    )

    if not push_tokens:
        logger.debug(f"No active push tokens for user {user_id}")
        return False

    # Send multicast notification
    success_count, failed_tokens = PushNotificationService.send_multicast_notification(
        tokens=push_tokens,
        title=title,
        body=body,
        data=data or {},
    )

    # Deactivate failed tokens
    if failed_tokens:
        PushToken.objects.filter(token__in=failed_tokens).update(is_active=False)
        logger.info(f"Deactivated {len(failed_tokens)} invalid push tokens")

    return success_count > 0


def send_push_notification_to_users(
    user_ids: List,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> int:
    """
    Send a push notification to multiple users' devices.

    Args:
        user_ids: List of user IDs to send notification to
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        Number of successful deliveries
    """
    from .models import PushToken

    if not user_ids:
        return 0

    # Get all active push tokens for these users
    push_tokens = list(
        PushToken.objects.filter(
            user_id__in=user_ids,
            is_active=True,
        ).values_list('token', flat=True)
    )

    if not push_tokens:
        logger.debug(f"No active push tokens for {len(user_ids)} users")
        return 0

    # Send multicast notification
    success_count, failed_tokens = PushNotificationService.send_multicast_notification(
        tokens=push_tokens,
        title=title,
        body=body,
        data=data or {},
    )

    # Deactivate failed tokens
    if failed_tokens:
        PushToken.objects.filter(token__in=failed_tokens).update(is_active=False)
        logger.info(f"Deactivated {len(failed_tokens)} invalid push tokens")

    return success_count


class PushNotificationService:
    """Service for sending push notifications via Firebase Cloud Messaging."""

    ANDROID_CHANNEL_ID = "reminders"

    @classmethod
    def send_notification(
        cls,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        device_type: str = "android",
    ) -> bool:
        """
        Send a push notification to a single device.

        Args:
            token: The FCM/APNs push token
            title: Notification title
            body: Notification body
            data: Optional data payload
            device_type: 'android', 'ios', or 'web'

        Returns:
            True if sent successfully, False otherwise
        """
        firebase_app = get_firebase_app()
        if not firebase_app:
            logger.warning("Firebase not initialized. Cannot send notification.")
            return False

        try:
            from firebase_admin import messaging

            # Build the message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id=cls.ANDROID_CHANNEL_ID,
                        priority="high",
                        default_sound=True,
                        default_vibrate_timings=True,
                        default_light_settings=True,
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound="default",
                            badge=1,
                        ),
                    ),
                ),
            )

            # Send the message
            response = messaging.send(message)
            logger.info(f"Push notification sent successfully: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False

    @classmethod
    def send_multicast_notification(
        cls,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> tuple[int, list[str]]:
        """
        Send a push notification to multiple devices.

        Automatically routes tokens:
        - Expo tokens (ExponentPushToken[...]) -> Expo Push Service
        - Native FCM tokens -> Firebase Cloud Messaging

        Args:
            tokens: List of push tokens (can be Expo or FCM format)
            title: Notification title
            body: Notification body
            data: Optional data payload

        Returns:
            Tuple of (successful_count, failed_tokens)
        """
        if not tokens:
            return (0, [])

        # Separate tokens by type
        expo_tokens, fcm_tokens = separate_tokens_by_type(tokens)

        total_success = 0
        all_failed_tokens = []

        # Send Expo tokens via Expo Push Service
        if expo_tokens:
            logger.info(f"Sending {len(expo_tokens)} notifications via Expo Push Service")
            success, failed = send_expo_notification(expo_tokens, title, body, data)
            total_success += success
            all_failed_tokens.extend(failed)

        # Send FCM tokens via Firebase
        if fcm_tokens:
            logger.info(f"Sending {len(fcm_tokens)} notifications via Firebase FCM")
            firebase_app = get_firebase_app()
            if not firebase_app:
                logger.warning("Firebase not initialized. Cannot send FCM notifications.")
                all_failed_tokens.extend(fcm_tokens)
            else:
                try:
                    from firebase_admin import messaging

                    # Build the multicast message
                    message = messaging.MulticastMessage(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data=data or {},
                        tokens=fcm_tokens,
                        android=messaging.AndroidConfig(
                            priority="high",
                            notification=messaging.AndroidNotification(
                                channel_id=cls.ANDROID_CHANNEL_ID,
                                priority="high",
                                default_sound=True,
                                default_vibrate_timings=True,
                                default_light_settings=True,
                            ),
                        ),
                        apns=messaging.APNSConfig(
                            payload=messaging.APNSPayload(
                                aps=messaging.Aps(
                                    sound="default",
                                    badge=1,
                                ),
                            ),
                        ),
                    )

                    # Send using send_each_for_multicast (firebase-admin 7.x+)
                    response = messaging.send_each_for_multicast(message)
                    logger.info(f"FCM push: {response.success_count} successful, {response.failure_count} failed")

                    total_success += response.success_count

                    # Extract failed tokens
                    if response.failure_count > 0:
                        for idx, resp in enumerate(response.responses):
                            if not resp.success:
                                all_failed_tokens.append(fcm_tokens[idx])
                                logger.warning(f"Failed to send to FCM token {fcm_tokens[idx][:20]}...: {resp.exception}")

                except Exception as e:
                    logger.error(f"Failed to send FCM multicast notification: {e}")
                    all_failed_tokens.extend(fcm_tokens)

        logger.info(f"Total notifications sent: {total_success} successful, {len(all_failed_tokens)} failed")
        return (total_success, all_failed_tokens)

    @classmethod
    def send_reminder_notification(
        cls,
        user,
        reminder_type: str,
        activity_id: Optional[str] = None,
        quiz_id: Optional[str] = None,
        course_section_id: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> bool:
        """
        Send a reminder notification to a user's devices.

        Args:
            user: The User object to send notification to
            reminder_type: 'activity' or 'quiz'
            activity_id: UUID of the activity (if activity reminder)
            quiz_id: UUID of the quiz (if quiz reminder)
            course_section_id: UUID of the course section for deep linking
            title: Optional custom title
            body: Optional custom body

        Returns:
            True if sent to at least one device, False otherwise
        """
        from .models import PushToken

        # Get all active push tokens for the user
        push_tokens = list(
            PushToken.objects.filter(user=user, is_active=True).values_list('token', flat=True)
        )

        if not push_tokens:
            logger.info(f"No active push tokens for user {user.id}")
            return False

        # Build notification content
        if not title:
            title = "Reminder"

        if not body:
            if reminder_type == "activity":
                body = "You have an upcoming assignment deadline."
            else:
                body = "You have an upcoming quiz deadline."

        # Build data payload for deep linking
        data = {
            "type": "reminder",
            "reminder_type": reminder_type,
        }

        if activity_id:
            data["activity_id"] = str(activity_id)

        if quiz_id:
            data["quiz_id"] = str(quiz_id)

        if course_section_id:
            data["course_section_id"] = str(course_section_id)

        # Send to all devices
        success_count, failed_tokens = cls.send_multicast_notification(
            tokens=push_tokens,
            title=title,
            body=body,
            data=data,
        )

        # Deactivate failed tokens
        if failed_tokens:
            PushToken.objects.filter(token__in=failed_tokens).update(is_active=False)
            logger.info(f"Deactivated {len(failed_tokens)} invalid push tokens")

        return success_count > 0