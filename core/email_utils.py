# hna-acadex-backend/core/email_utils.py
"""
Email utilities for HNA Acadex.

Supports two email backends:
1. Brevo API (production) - Default, uses Brevo's transactional email API
2. Gmail SMTP (development) - Uses Django's SMTP backend with Gmail

Toggle via EMAIL_BACKEND_TYPE setting:
- 'brevo' (default for production)
- 'smtp' (for development)
"""

import secrets
import string
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

# App download link
APP_DOWNLOAD_URL = "https://expo.dev/accounts/hnaadmin/projects/hna-acadex/builds/e7666875-8ec9-4bf2-a4c0-307c4f18d2e7"

# Email button styles - designed to work in both light and dark modes
# Using solid colors with high contrast and a border for visibility
EMAIL_BUTTON_STYLE = """
    background-color: #4F46E5;
    color: #ffffff;
    padding: 14px 28px;
    text-decoration: none;
    border-radius: 8px;
    border: 2px solid #4F46E5;
    display: inline-block;
    font-weight: bold;
    font-size: 16px;
"""


def get_email_backend_type():
    """
    Get the configured email backend type.

    Returns:
        str: 'brevo' or 'smtp' based on EMAIL_BACKEND_TYPE setting

    Note:
        Defaults to 'brevo' for production safety.
        Set EMAIL_BACKEND_TYPE=smtp in .env for development.
    """
    return getattr(settings, 'EMAIL_BACKEND_TYPE', 'brevo').lower()


def get_brevo_client():
    """Get Brevo Transactional Emails API client with configured API key."""
    try:
        from brevo_python import ApiClient, Configuration, TransactionalEmailsApi
        api_key = getattr(settings, 'BREVO_API_KEY', None)
        if not api_key:
            raise ValueError("BREVO_API_KEY not configured in settings")
        configuration = Configuration()
        configuration.api_key['api-key'] = api_key
        return TransactionalEmailsApi(ApiClient(configuration))
    except ImportError:
        raise ImportError("brevo-python package not installed. Run: pip install brevo-python")


def send_email_via_brevo(to_email, subject, html_content, plain_content=None):
    """
    Send email using Brevo's Transactional Emails API.

    This is faster than SMTP and works well on free tier without background workers.
    Used for production environments.
    """
    try:
        from brevo_python import SendSmtpEmail, SendSmtpEmailSender, SendSmtpEmailTo
        client = get_brevo_client()
        sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'hnaacadexadmin@gmail.com')

        response = client.send_transac_email(
            SendSmtpEmail(
                html_content=html_content,
                text_content=plain_content or html_content,
                sender=SendSmtpEmailSender(
                    email=sender_email,
                    name="HNA Acadex",
                ),
                subject=subject,
                to=[SendSmtpEmailTo(email=to_email)],
            )
        )

        logger.info(f"Email sent via Brevo to {to_email}: {response}")
        return True, f"Email sent to {to_email}"
    except Exception as e:
        logger.error(f"Brevo API error sending to {to_email}: {e}")
        return False, f"Failed to send email: {e}"


def send_email_via_smtp(to_email, subject, html_content, plain_content=None):
    """
    Send email using Django's SMTP backend.

    This is useful for development when you want to test emails
    without using Brevo's API. Works with Gmail SMTP (requires app password).

    Setup for Gmail:
    1. Enable 2-factor authentication on your Google account
    2. Generate an App Password: https://myaccount.google.com/apppasswords
    3. Set EMAIL_HOST_PASSWORD in .env to the app password
    """
    try:
        sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'hnaacadexadmin@gmail.com')

        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_content or html_content,
            from_email=sender_email,
            to=[to_email],
        )

        if html_content:
            email.attach_alternative(html_content, "text/html")

        email.send()

        logger.info(f"Email sent via SMTP to {to_email}")
        return True, f"Email sent to {to_email}"
    except Exception as e:
        logger.error(f"SMTP error sending to {to_email}: {e}")
        return False, f"Failed to send email: {e}"


def send_email(to_email, subject, html_content, plain_content=None):
    """
    Send email using the configured backend (Brevo or SMTP).

    This is the main entry point for sending emails. It automatically
    selects the appropriate backend based on EMAIL_BACKEND_TYPE setting.

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML version of the email
        plain_content: Plain text version (optional, defaults to html_content)

    Returns:
        tuple: (success: bool, message: str)

    Usage:
        # In settings.py or .env:
        # For production (Brevo):
        EMAIL_BACKEND_TYPE=brevo
        BREVO_API_KEY=your-brevo-api-key

        # For development (Gmail SMTP):
        EMAIL_BACKEND_TYPE=smtp
        EMAIL_HOST=smtp.gmail.com
        EMAIL_PORT=587
        EMAIL_USE_TLS=True
        EMAIL_HOST_USER=your-email@gmail.com
        EMAIL_HOST_PASSWORD=your-app-password
    """
    backend_type = get_email_backend_type()

    if backend_type == 'smtp':
        logger.debug(f"Using SMTP backend for email to {to_email}")
        return send_email_via_smtp(to_email, subject, html_content, plain_content)
    else:
        # Default to Brevo for production
        logger.debug(f"Using Brevo backend for email to {to_email}")
        return send_email_via_brevo(to_email, subject, html_content, plain_content)


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
    """Send login credentials to the user's personal email."""
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
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <style>
        /* Base styles */
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f9fafb;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .header {{
            background-color: #4F46E5;
            color: #ffffff;
            padding: 30px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            padding: 30px 20px;
            background-color: #ffffff;
        }}
        .credentials {{
            background-color: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border: 1px solid #e5e7eb;
        }}
        .credential-item {{
            margin: 12px 0;
        }}
        .credential-label {{
            font-weight: bold;
            color: #6b7280;
            font-size: 14px;
        }}
        .credential-value {{
            font-family: 'Courier New', monospace;
            background-color: #f3f4f6;
            padding: 10px 14px;
            border-radius: 6px;
            display: inline-block;
            margin-top: 4px;
            font-size: 15px;
            color: #111827;
            border: 1px solid #e5e7eb;
        }}
        .warning {{
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .warning strong {{
            color: #92400e;
        }}
        .button-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .app-button {{
            background-color: #4F46E5;
            color: #ffffff;
            padding: 14px 28px;
            text-decoration: none;
            border-radius: 8px;
            border: 2px solid #4F46E5;
            display: inline-block;
            font-weight: bold;
            font-size: 16px;
        }}
        .app-button:hover {{
            background-color: #4338CA;
            border-color: #4338CA;
        }}
        .footer {{
            text-align: center;
            color: #9ca3af;
            font-size: 12px;
            padding: 20px;
            border-top: 1px solid #e5e7eb;
            background-color: #f9fafb;
        }}

        /* Dark mode support */
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #1f2937;
                color: #f3f4f6;
            }}
            .container {{
                background-color: #374151;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
            .content {{
                background-color: #374151;
            }}
            .credentials {{
                background-color: #4b5563;
                border-color: #6b7280;
            }}
            .credential-label {{
                color: #d1d5db;
            }}
            .credential-value {{
                background-color: #4b5563;
                color: #f9fafb;
                border-color: #6b7280;
            }}
            .warning {{
                background-color: #78350f;
                border-color: #fbbf24;
            }}
            .warning strong {{
                color: #fcd34d;
            }}
            .app-button {{
                background-color: #6366f1;
                border-color: #6366f1;
                color: #ffffff;
            }}
            .app-button:hover {{
                background-color: #4f46e5;
                border-color: #4f46e5;
            }}
            .footer {{
                background-color: #374151;
                border-top-color: #4b5563;
                color: #9ca3af;
            }}
        }}
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
                <h3 style="margin-top: 0; margin-bottom: 16px; color: #374151;">Your Login Credentials</h3>
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
            <div class="button-container">
                <a href="{APP_DOWNLOAD_URL}" class="app-button" style="background-color: #4F46E5; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; border: 2px solid #4F46E5; display: inline-block; font-weight: bold; font-size: 16px;">Download the App</a>
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

    return send_email(
        to_email=user.personal_email,
        subject=subject,
        html_content=html_message.strip(),
        plain_content=plain_message.strip(),
    )


def send_password_reset_email(user, new_password):
    """Send password reset email to the user's personal email."""
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
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <style>
        /* Base styles */
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f9fafb;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .header {{
            background-color: #DC2626;
            color: #ffffff;
            padding: 30px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            padding: 30px 20px;
            background-color: #ffffff;
        }}
        .credentials {{
            background-color: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border: 1px solid #e5e7eb;
        }}
        .credential-item {{
            margin: 12px 0;
        }}
        .credential-label {{
            font-weight: bold;
            color: #6b7280;
            font-size: 14px;
        }}
        .credential-value {{
            font-family: 'Courier New', monospace;
            background-color: #f3f4f6;
            padding: 10px 14px;
            border-radius: 6px;
            display: inline-block;
            margin-top: 4px;
            font-size: 15px;
            color: #111827;
            border: 1px solid #e5e7eb;
        }}
        .warning {{
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .warning strong {{
            color: #92400e;
        }}
        .button-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .app-button {{
            background-color: #4F46E5;
            color: #ffffff;
            padding: 14px 28px;
            text-decoration: none;
            border-radius: 8px;
            border: 2px solid #4F46E5;
            display: inline-block;
            font-weight: bold;
            font-size: 16px;
        }}
        .app-button:hover {{
            background-color: #4338CA;
            border-color: #4338CA;
        }}
        .footer {{
            text-align: center;
            color: #9ca3af;
            font-size: 12px;
            padding: 20px;
            border-top: 1px solid #e5e7eb;
            background-color: #f9fafb;
        }}

        /* Dark mode support */
        @media (prefers-color-scheme: dark) {{
            body {{
                background-color: #1f2937;
                color: #f3f4f6;
            }}
            .container {{
                background-color: #374151;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
            .content {{
                background-color: #374151;
            }}
            .credentials {{
                background-color: #4b5563;
                border-color: #6b7280;
            }}
            .credential-label {{
                color: #d1d5db;
            }}
            .credential-value {{
                background-color: #4b5563;
                color: #f9fafb;
                border-color: #6b7280;
            }}
            .warning {{
                background-color: #78350f;
                border-color: #fbbf24;
            }}
            .warning strong {{
                color: #fcd34d;
            }}
            .app-button {{
                background-color: #6366f1;
                border-color: #6366f1;
                color: #ffffff;
            }}
            .app-button:hover {{
                background-color: #4f46e5;
                border-color: #4f46e5;
            }}
            .footer {{
                background-color: #374151;
                border-top-color: #4b5563;
                color: #9ca3af;
            }}
        }}
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
                <h3 style="margin-top: 0; margin-bottom: 16px; color: #374151;">Your New Login Credentials</h3>
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
            <div class="button-container">
                <a href="{APP_DOWNLOAD_URL}" class="app-button" style="background-color: #4F46E5; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; border: 2px solid #4F46E5; display: inline-block; font-weight: bold; font-size: 16px;">Download the App</a>
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

    return send_email(
        to_email=user.personal_email,
        subject=subject,
        html_content=html_message.strip(),
        plain_content=plain_message.strip(),
    )
