from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from academics.models import Semester, Subject, Topic
from notifications.models import Notification
from tasks.models import SubmissionLink, Task, TaskAttachment, TaskComment, TaskProgress

from .models import GroupInvitation, GroupMembership, JoinRequest, StudentProfile, StudyGroup

pytestmark = pytest.mark.django_db


def counts():
    models = (
        get_user_model(),
        StudyGroup,
        GroupMembership,
        Semester,
        Subject,
        Topic,
        Task,
        TaskProgress,
        TaskComment,
        TaskAttachment,
        SubmissionLink,
        GroupInvitation,
        JoinRequest,
        Notification,
    )
    return tuple(model.objects.count() for model in models)


def test_demo_is_repeatable_and_preserves_real_records_and_test_changes(settings, tmp_path, student_factory):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    real = student_factory()
    original_profile = StudentProfile.objects.get(user=real)
    original_name = original_profile.first_name
    call_command("seed_demo", attach_user_id=real.pk, stdout=StringIO())
    first_counts = counts()
    assert StudyGroup.objects.count() == 2
    assert Semester.objects.filter(is_active=True).count() == 2
    assert Task.objects.count() == 48
    assert set(TaskProgress.objects.values_list("status", flat=True)) == set(TaskProgress.Status.values)
    assert Task.objects.filter(deadline__lt=timezone.now()).exists()
    assert JoinRequest.objects.filter(status=JoinRequest.Status.PENDING).count() == 2
    assert GroupMembership.objects.filter(user=real).count() == 2
    task = Task.objects.first()
    task.description = "Мій змінений опис"
    task.save(update_fields=["description"])
    owner = get_user_model().objects.get(username="studhub_demo_owner")
    owner.set_password("Changed-demo-password!2026")
    owner.save(update_fields=["password"])
    original_hash = owner.password
    progress = TaskProgress.objects.filter(task=task, user=owner).first()
    progress.status = TaskProgress.Status.GRADED
    progress.save()
    call_command("seed_demo", attach_user_id=real.pk, stdout=StringIO())
    assert counts() == first_counts
    owner.refresh_from_db()
    task.refresh_from_db()
    progress.refresh_from_db()
    real.student_profile.refresh_from_db()
    assert owner.password == original_hash
    assert task.description == "Мій змінений опис"
    assert progress.status == TaskProgress.Status.GRADED
    assert real.student_profile.first_name == original_name
    assert EmailAddress.objects.filter(user=owner, verified=True).exists()
    attachment = TaskAttachment.objects.get()
    assert attachment.file.storage.exists(attachment.file.name)


def test_demo_refuses_account_collisions_atomically(settings, student_factory):
    settings.DEBUG = True
    user = student_factory()
    user.username = "studhub_demo_deputy"
    user.save(update_fields=["username"])
    before = counts()
    with pytest.raises(CommandError, match="Конфлікт"):
        call_command("seed_demo", stdout=StringIO())
    assert counts() == before


def test_demo_requires_local_development_settings(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo", stdout=StringIO())
    assert not StudyGroup.objects.exists()
