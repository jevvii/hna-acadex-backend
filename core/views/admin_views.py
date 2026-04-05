"""
Admin-related views for administrative operations.
"""
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuditLog, Course, PasswordResetRequest, Section, User
from core.permissions import IsAdminRole
from core.serializers import PasswordResetRequestSerializer


class DashboardStatsView(APIView):
    """Admin-only view for dashboard statistics."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        data = {
            "students": User.objects.filter(role=User.Role.STUDENT).count(),
            "teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "courses": Course.objects.filter(is_active=True).count(),
            "sections": Section.objects.filter(is_active=True).count(),
        }
        return Response(data)


class PasswordResetRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin viewset for managing password reset requests."""
    permission_classes = [IsAdminRole]
    queryset = PasswordResetRequest.objects.select_related("user", "resolved_by").all()
    serializer_class = PasswordResetRequestSerializer

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve a password reset request and send new credentials."""
        from core.email_utils import generate_random_password, send_password_reset_email

        reset_request = self.get_object()

        if reset_request.status != PasswordResetRequest.Status.PENDING:
            return Response(
                {"detail": "This request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = reset_request.user

        # Generate new password
        new_password = generate_random_password()
        user.set_password(new_password)
        user.requires_setup = True
        user.save(update_fields=["password", "requires_setup", "updated_at"])

        # Send email
        success, message = send_password_reset_email(user, new_password)

        if success:
            # Update request status
            reset_request.status = PasswordResetRequest.Status.APPROVED
            reset_request.resolved_at = timezone.now()
            reset_request.resolved_by = request.user
            reset_request.save()

            # Audit log the password reset approval
            AuditLog.log(
                request,
                action='password_reset_approved',
                target_type='PasswordResetRequest',
                target_id=None,  # Can't store UUID in IntegerField
                details={'reset_request_id': str(reset_request.id), 'user_email': user.email, 'sent_to': user.personal_email}
            )

            return Response({
                "detail": f"Password reset approved. New credentials sent to {user.personal_email}"
            })
        else:
            return Response(
                {"detail": f"Failed to send email: {message}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        """Decline a password reset request."""
        reset_request = self.get_object()

        if reset_request.status != PasswordResetRequest.Status.PENDING:
            return Response(
                {"detail": "This request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reset_request.status = PasswordResetRequest.Status.DECLINED
        reset_request.resolved_at = timezone.now()
        reset_request.resolved_by = request.user
        reset_request.save()

        # Audit log the password reset decline
        AuditLog.log(
            request,
            action='password_reset_declined',
            target_type='PasswordResetRequest',
            target_id=None,  # Can't store UUID in IntegerField
            details={'reset_request_id': str(reset_request.id), 'user_email': reset_request.user.email}
        )

        return Response({"detail": "Password reset request declined."})


__all__ = [
    'DashboardStatsView',
    'PasswordResetRequestViewSet',
]