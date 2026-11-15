import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError

from students.models import StudyGroup

from .models import Notification
from .services import list_notifications, mark_read

pytestmark = pytest.mark.django_db


def test_inbox_and_mark_read_are_recipient_scoped(django_user_model):
    first = django_user_model.objects.create_user(username="first")
    second = django_user_model.objects.create_user(username="second")
    group = StudyGroup.objects.create(owner=first, name="Група")
    own = Notification.objects.create(
        recipient=first, group=group, kind=Notification.Kind.INVITATION, title="Запрошення"
    )
    other = Notification.objects.create(recipient=second, group=group, kind=Notification.Kind.INVITATION, title="Інше")
    assert list(list_notifications(first, unread_only=True)) == [own]
    assert mark_read(first, other.pk) == 0
    assert mark_read(first) == 1
    own.refresh_from_db()
    read_at = own.read_at
    assert mark_read(first) == 0
    own.refresh_from_db()
    other.refresh_from_db()
    assert own.read_at == read_at
    assert other.read_at is None
    with pytest.raises(PermissionDenied):
        list_notifications(AnonymousUser())


def test_invitation_notification_cannot_reference_another_group(django_user_model):
    user = django_user_model.objects.create_user(username="recipient")
    first = StudyGroup.objects.create(owner=user, name="Перша")
    second = StudyGroup.objects.create(owner=user, name="Друга")
    invitation = first.invitations.create(created_by=user)
    notice = Notification(
        recipient=user, group=second, invitation=invitation, kind=Notification.Kind.INVITATION, title="Запрошення"
    )
    with pytest.raises(ValidationError):
        notice.full_clean()
