# hna-acadex-backend/core/email_utils.py
import secrets
import string
import logging
from django.conf import settings
from brevo import Brevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem

logger = logging.getLogger(__name__)

# App download link
APP_DOWNLOAD_URL = "https://expo.dev/accounts/hnaadmin/projects/hna-acadex/builds/e7666875-8ec9-4bf2-a4c0-307c4f18d2e7"


def get_brevo_client():
    """Get Brevo client with configured API key."""
    api_key = getattr(settings, 'BREVO_API_KEY', None)
    if not api_key:
        raise ValueError("BREVO_API_KEY not configured in settings")
    return Brevo(api_key=api_key)


def send_email_via_brevo(to_email, subject, html_content, plain_content=None):
    """
    Send email using Brevo's Transactional Emails API.

    This is faster than SMTP and works well on free tier without background workers.
    """
    try:
        client = get_brevo_client()
        sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'hnaacadexadmin@gmail.com')

        response = client.transactional_emails.send_transac_email(
            html_content=html_content,
            text_content=plain_content or html_content,
            sender=SendTransacEmailRequestSender(
                email=sender_email,
                name="HNA Acadex",
            ),
            subject=subject,
            to=[SendTransacEmailRequestToItem(email=to_email)],
        )

        logger.info(f"Email sent via Brevo to {to_email}: {response}")
        return True, f"Email sent to {to_email}"
    except Exception as e:
        logger.error(f"Brevo API error sending to {to_email}: {e}")
        return False, f"Failed to send email: {e}"


def generate_random_password(length=12):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def get_role_display(role_value):
    """Get the display name for a role value."""
    role_choices = {
        'admin': 'Admin',
        'teacher': 'Teacher',
        'student': 'Student',
    }
    return role_choices.get(role_value, role_value)


def send_credentials_email(user, plain_password):
    """Send login credentials to the user's personal email via Brevo API."""
    if not user.personal_email:
        return False, "No personal email address provided."

    role_display = get_role_display(user.role)
    subject = f"Welcome to HNA Acadex - Your {role_display} Account Credentials"
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8081')

    plain_message = f"""
Dear {user.full_name},

Welcome to HNA Acadex! Your {role_display} account has been created.

Here are your login credentials:

Email: {user.email}
Password: {plain_password}

Please log in and change your password as soon as possible.

Download the app: {APP_DOWNLOAD_URL}

If you have any questions, please contact the administrator.

Best regards,
HNA Acadex Team
    """

    html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4F46E5; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
        .credentials {{ background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e5e7eb; }}
        .credential-item {{ margin: 10px 0; }}
        .credential-label {{ font-weight: bold; color: #6b7280; }}
        .credential-value {{ font-family: monospace; background-color: #f3f4f6; padding: 8px 12px; border-radius: 4px; display: inline-block; }}
        .warning {{ background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0; }}
        .app-button {{ display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 15px 0; }}
        .app-button:hover {{ background-color: #4338CA; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to HNA Acadex</h1>
        </div>
        <div class="content">
            <p>Dear {user.full_name},</p>
            <p>Welcome to HNA Acadex! Your <strong>{role_display}</strong> account has been created.</p>
            <div class="credentials">
                <h3 style="margin-top: 0;">Your Login Credentials</h3>
                <div class="credential-item">
                    <span class="credential-label">Email:</span><br>
                    <span class="credential-value">{user.email}</span>
                </div>
                <div class="credential-item">
                    <span class="credential-label">Password:</span><br>
                    <span class="credential-value">{plain_password}</span>
                </div>
            </div>
            <div class="warning">
                <strong>Important:</strong> Please log in and change your password as soon as possible.
            </div>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{APP_DOWNLOAD_URL}" class="app-button">Download the App</a>
            </div>
            <p>Best regards,<br>HNA Acadex Team</p>
        </div>
        <div class="footer">
            This is an automated message. Please do not reply to this email.
        </div>
    </div>
</body>
</html>
    """

    return send_email_via_brevo(
        to_email=user.personal_email,
        subject=subject,
        html_content=html_message.strip(),
        plain_content=plain_message.strip(),
    )


def send_password_reset_email(user, new_password):
    """Send password reset email to the user's personal email via Brevo API."""
    if not user.personal_email:
        return False, "No personal email address provided."

    role_display = get_role_display(user.role)
    subject = f"Password Reset - HNA Acadex {role_display} Account"

    plain_message = f"""
Dear {user.full_name},

Your password has been reset by the administrator.

Here are your new login credentials:

Email: {user.email}
New Password: {new_password}

Please log in and change your password as soon as possible.

Download the app: {APP_DOWNLOAD_URL}

If you did not request this password reset, please contact the administrator immediately.

Best regards,
HNA Acadex Team
    """

    html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #DC2626; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
        .credentials {{ background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e5e7eb; }}
        .credential-item {{ margin: 10px 0; }}
        .credential-label {{ font-weight: bold; color: #6b7280; }}
        .credential-value {{ font-family: monospace; background-color: #f3f4f6; padding: 8px 12px; border-radius: 4px; display: inline-block; }}
        .warning {{ background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0; }}
        .app-button {{ display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 15px 0; }}
        .app-button:hover {{ background-color: #4338CA; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset</h1>
        </div>
        <div class="content">
            <p>Dear {user.full_name},</p>
            <p>Your password has been reset by the administrator.</p>
            <div class="credentials">
                <h3 style="margin-top: 0;">Your New Login Credentials</h3>
                <div class="credential-item">
                    <span class="credential-label">Email:</span><br>
                    <span class="credential-value">{user.email}</span>
                </div>
                <div class="credential-item">
                    <span class="credential-label">New Password:</span><br>
                    <span class="credential-value">{new_password}</span>
                </div>
            </div>
            <div class="warning">
                <strong>Important:</strong> Please log in and change your password as soon as possible.
            </div>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{APP_DOWNLOAD_URL}" class="app-button">Download the App</a>
            </div>
            <p>Best regards,<br>HNA Acadex Team</p>
        </div>
        <div class="footer">
            This is an automated message. Please do not reply to this email.
        </div>
    </div>
</body>
</html>
    """

    return send_email_via_brevo(
        to_email=user.personal_email,
        subject=subject,
        html_content=html_message.strip(),
        plain_content=plain_message.strip(),
    )