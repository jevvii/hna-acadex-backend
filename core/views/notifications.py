"""
Notification-related views.
"""
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import Notification, User
from core.serializers import NotificationSerializer
from core.pagination import NotificationPagination
from core.views.common import _sync_daily_active_notifications_best_effort


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        if self.request.user.role in {User.Role.STUDENT, User.Role.TEACHER}:
            _sync_daily_active_notifications_best_effort(self.request.user)
        return Notification.objects.filter(recipient=self.request.user).order_by("-created_at")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notif).data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({"ok": True})


__all__ = [
    'NotificationViewSet',
]
