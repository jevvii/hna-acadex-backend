# hna-acadex-backend/core/email_utils.py
import secrets
import string
from django.core.mail import send_mail
from django.conf import settings


def generate_random_password(length=12):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each character type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    # Fill the rest with random characters
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    # Shuffle to avoid predictable pattern
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def get_role_display(role_value):
    """Get the display name for a role value."""
    # Role choices mapping
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

    # Plain text version
    plain_message = f"""
Dear {user.full_name},

Welcome to HNA Acadex! Your {role_display} account has been created.

Here are your login credentials:

Email: {user.email}
Password: {plain_password}

Please log in and change your password as soon as possible.

Login URL: {frontend_url}

If you have any questions, please contact the administrator.

Best regards,
HNA Acadex Team
    """

    # HTML version
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
                <strong>Important:</strong> Please log in and change your password as soon as possible for security reasons.
            </div>

            <p style="margin-top: 20px;">
                You can log in at: <a href="{frontend_url}">{frontend_url}</a>
            </p>

            <p>If you have any questions, please contact the administrator.</p>

            <p>Best regards,<br>HNA Acadex Team</p>
        </div>
        <div class="footer">
            This is an automated message. Please do not reply to this email.
        </div>
    </div>
</body>
</html>
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.personal_email],
            html_message=html_message.strip(),
            fail_silently=True,  # Don't block on email failures
        )
        return True, f"Credentials sent successfully to {user.personal_email}"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def send_password_reset_email(user, new_password):
    """Send password reset email to the user's personal email."""
    if not user.personal_email:
        return False, "No personal email address provided."

    role_display = get_role_display(user.role)

    subject = f"Password Reset - HNA Acadex {role_display} Account"

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8081')

    # Plain text version
    plain_message = f"""
Dear {user.full_name},

Your password has been reset by the administrator.

Here are your new login credentials:

Email: {user.email}
New Password: {new_password}

Please log in and change your password as soon as possible.

Login URL: {frontend_url}

If you did not request this password reset, please contact the administrator immediately.

Best regards,
HNA Acadex Team
    """

    # HTML version
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
                <strong>Important:</strong> Please log in and change your password as soon as possible for security reasons.
            </div>

            <p style="margin-top: 20px;">
                You can log in at: <a href="{frontend_url}">{frontend_url}</a>
            </p>

            <p>If you did not request this password reset, please contact the administrator immediately.</p>

            <p>Best regards,<br>HNA Acadex Team</p>
        </div>
        <div class="footer">
            This is an automated message. Please do not reply to this email.
        </div>
    </div>
</body>
</html>
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.personal_email],
            html_message=html_message.strip(),
            fail_silently=True,  # Don't block on email failures
        )
        return True, f"Password reset email sent successfully to {user.personal_email}"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"