from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import Notification


def list_notifications(user, *, unread_only=False):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    notifications = Notification.objects.filter(recipient=user).select_related("group", "task")
    return notifications.filter(read_at__isnull=True) if unread_only else notifications


def mark_read(user, notification_id=None):
    notifications = list_notifications(user, unread_only=True)
    if notification_id is not None:
        notifications = notifications.filter(pk=notification_id)
    return notifications.update(read_at=timezone.now())
