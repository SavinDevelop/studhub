from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import Semester, Subject, Topic
from students.models import StudyGroup

from .models import SubmissionLink, Task
from .services import create_task, delete_task, get_task, list_tasks, update_task

pytestmark = pytest.mark.django_db


@pytest.fixture
def task_data(django_user_model):
    user = django_user_model.objects.create_user(username="task_owner")
    group = StudyGroup.objects.create(name="КН-21", owner=user)
    semester = Semester.objects.create(
        group=group, name="Осінь", academic_year_start=2026, starts_on=date(2026, 9, 1), ends_on=date(2026, 12, 31)
    )
    subject = Subject.objects.create(semester=semester, name="Алгоритми", teacher_name="Викладач")
    topic = Topic.objects.create(subject=subject, name="Сортування масивів")
    return {
        "title": "Лабораторна робота №1",
        "topic": topic,
        "subject": subject,
        "deadline": timezone.now() + timedelta(days=7),
        "description": "Реалізувати та порівняти алгоритми сортування.",
        "submission_links": ["https://classroom.google.com/", "https://example.com/submit"],
    }


def test_create_task_persists_details_and_links(task_data):
    task = create_task(**task_data)
    saved = get_task(task.pk)
    for field in ("title", "topic", "subject", "deadline", "description"):
        assert getattr(saved, field) == task_data[field]
    assert saved.is_required is True
    assert list(saved.submission_links.values_list("url", flat=True)) == task_data["submission_links"]


def test_optional_task_without_description_or_links(task_data):
    task_data.pop("description")
    task_data.pop("submission_links")
    task = create_task(**task_data, is_required=False)
    assert task.is_required is False
    assert task.description == ""
    assert not task.submission_links.exists()


@pytest.mark.parametrize("field", ["title"])
@pytest.mark.parametrize("value", ["", "   ", "x" * 256])
def test_required_text_validation_rolls_back_creation(task_data, field, value):
    task_data[field] = value
    with pytest.raises(ValidationError):
        create_task(**task_data)
    assert not Task.objects.exists()
    assert not SubmissionLink.objects.exists()


@pytest.mark.parametrize("url", ["not-a-url", "javascript:alert(1)", "ftp://example.com/file", ""])
def test_invalid_link_rolls_back_task(task_data, url):
    task_data["submission_links"] = ["https://example.com/valid", url]
    with pytest.raises(ValidationError):
        create_task(**task_data)
    assert not Task.objects.exists()
    assert not SubmissionLink.objects.exists()


def test_duplicate_links_rejected(task_data):
    task_data["submission_links"] = ["https://example.com/", " https://example.com/ "]
    with pytest.raises(ValidationError):
        create_task(**task_data)
    assert not Task.objects.exists()


@pytest.mark.parametrize("deadline", [None, "not-a-date"])
def test_invalid_deadline_rejected(task_data, deadline):
    task_data["deadline"] = deadline
    with pytest.raises(ValidationError):
        create_task(**task_data)


@pytest.mark.parametrize("as_string", [False, True])
def test_naive_deadline_rejected(task_data, as_string):
    deadline = task_data["deadline"].replace(tzinfo=None)
    task_data["deadline"] = deadline.isoformat() if as_string else deadline
    with pytest.raises(ValidationError, match="часовий пояс"):
        create_task(**task_data)


@pytest.mark.parametrize("urls", [None, "https://example.com/", 42])
def test_links_must_be_a_collection(task_data, urls):
    task_data["submission_links"] = urls
    with pytest.raises(ValidationError, match="список посилань"):
        create_task(**task_data)
    assert not Task.objects.exists()


def test_past_deadline_allowed(task_data):
    task_data["deadline"] = timezone.now() - timedelta(days=1)
    assert create_task(**task_data).deadline == task_data["deadline"]


def test_update_preserves_unspecified_fields_and_links(task_data):
    task = create_task(**task_data)
    updated = update_task(task.pk, title="  Нова назва  ", is_required=False)
    assert updated.title == "Нова назва"
    assert updated.is_required is False
    assert updated.subject == task_data["subject"]
    assert updated.submission_links.count() == 2


def test_update_replaces_and_clears_links(task_data):
    task = create_task(**task_data)
    update_task(task.pk, submission_links=["https://example.org/new"])
    assert list(task.submission_links.values_list("url", flat=True)) == ["https://example.org/new"]
    update_task(task.pk, submission_links=[])
    assert not task.submission_links.exists()


def test_invalid_link_update_rolls_back_all_changes(task_data):
    task = create_task(**task_data)
    with pytest.raises(ValidationError):
        update_task(task.pk, title="Змінена назва", submission_links=["invalid"])
    task.refresh_from_db()
    assert task.title == task_data["title"]
    assert list(task.submission_links.values_list("url", flat=True)) == task_data["submission_links"]


def test_invalid_field_update_preserves_existing_task(task_data):
    task = create_task(**task_data)
    with pytest.raises(ValidationError):
        update_task(task.pk, title=" ")
    task.refresh_from_db()
    assert task.title == task_data["title"]


def test_update_rejects_noneditable_fields(task_data):
    task = create_task(**task_data)
    with pytest.raises(ValidationError):
        update_task(task.pk, created_at=timezone.now())


def test_list_filters_and_orders_by_deadline(task_data):
    later = create_task(**task_data)
    earlier = create_task(**{**task_data, "deadline": later.deadline - timedelta(days=1), "is_required": False})
    physics = Subject.objects.create(semester=later.subject.semester, name="Фізика", teacher_name="Викладач")
    create_task(**{**task_data, "subject": physics, "topic": None})
    assert list(list_tasks(subject="алгоритми")) == [earlier, later]
    assert list(list_tasks(is_required=False)) == [earlier]
    assert list(list_tasks(subject="Алгоритми", deadline_from=later.deadline, deadline_to=later.deadline)) == [later]


def test_delete_task_cascades_links(task_data):
    task = create_task(**task_data)
    delete_task(task.pk)
    assert not Task.objects.exists()
    assert not SubmissionLink.objects.exists()


@pytest.mark.parametrize("operation", [get_task, update_task, delete_task])
def test_missing_task_raises(operation):
    with pytest.raises(Task.DoesNotExist):
        operation(999)


def test_topic_must_belong_to_task_subject(task_data):
    other = Subject.objects.create(semester=task_data["subject"].semester, name="Інше", teacher_name="Викладач")
    with pytest.raises(ValidationError, match="Тема повинна"):
        create_task(**{**task_data, "subject": other})
    assert not Task.objects.exists()


def test_new_task_requires_subject(task_data):
    with pytest.raises(ValidationError):
        create_task(**{**task_data, "subject": None, "topic": None})


@pytest.fixture
def task_users(task_data, django_user_model):
    from students.models import GroupMembership, StudentProfile

    group = task_data["subject"].group
    owner = group.owner
    member = django_user_model.objects.create_user(username="task_member")
    outsider = django_user_model.objects.create_user(username="outsider")
    for user in (owner, member, outsider):
        StudentProfile.objects.create(user=user, first_name="Ім'я", last_name="Прізвище", completed_at=timezone.now())
    for user in (owner, member):
        GroupMembership.objects.create(user=user, group=group)
    return owner, member, outsider


def test_progress_is_per_student_and_overdue_is_derived(task_data, task_users):
    from django.core.exceptions import PermissionDenied
    from django.db import IntegrityError, transaction

    from .models import TaskProgress
    from .services import set_task_status

    owner, member, outsider = task_users
    task = create_task(**{**task_data, "deadline": timezone.now() - timedelta(days=1)})
    own = set_task_status(owner, task.pk, status=TaskProgress.Status.COMPLETED)
    theirs = set_task_status(member, task.pk, status=TaskProgress.Status.IN_PROGRESS)
    assert not own.is_overdue
    assert theirs.is_overdue
    assert set_task_status(owner, task.pk, status=TaskProgress.Status.GRADED).pk == own.pk
    theirs.refresh_from_db()
    assert theirs.status == TaskProgress.Status.IN_PROGRESS
    with pytest.raises(PermissionDenied):
        set_task_status(outsider, task.pk, status=TaskProgress.Status.GRADED)
    with pytest.raises(ValidationError):
        set_task_status(member, task.pk, status="invalid")
    with pytest.raises(IntegrityError), transaction.atomic():
        TaskProgress.objects.create(task=task, user=owner)


def test_task_creation_and_comments_enforce_group_permissions(task_data, task_users):
    from django.core.exceptions import PermissionDenied

    from .services import add_comment, create_group_task

    owner, member, outsider = task_users
    task = create_group_task(owner, **task_data)
    assert task.created_by == owner
    with pytest.raises(PermissionDenied):
        create_group_task(member, **task_data)
    with pytest.raises(PermissionDenied):
        add_comment(outsider, task.pk, body="Чужий коментар")
    with pytest.raises(ValidationError):
        add_comment(member, task.pk, body=" ")
    with pytest.raises(ValidationError):
        add_comment(member, task.pk, body="Текст", mentioned_user_ids=[outsider.pk])
    comment = add_comment(member, task.pk, body="  Дякую!  ", mentioned_user_ids=[owner.pk])
    assert comment.body == "Дякую!"
    assert list(comment.mentions.all()) == [owner]


@pytest.mark.parametrize(
    ("has_file", "has_url", "valid"),
    [(False, False, False), (True, True, False), (True, False, True), (False, True, True)],
)
def test_attachment_has_exactly_one_source(task_data, has_file, has_url, valid):
    from django.core.files.base import ContentFile

    from .models import TaskAttachment

    task = create_task(**task_data)
    attachment = TaskAttachment(
        task=task,
        name="Методичка",
        file=ContentFile(b"material", name="guide.pdf") if has_file else "",
        url="https://example.com/guide" if has_url else "",
    )
    if valid:
        attachment.full_clean()
    else:
        with pytest.raises(ValidationError):
            attachment.full_clean()
