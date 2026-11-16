"""Task CRUD with validation and atomic replacement of submission links.

This layer does not authorize callers. Views must check permissions before calling it.
Past deadlines are allowed so existing assignments can be recorded.
"""

from datetime import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from students.models import GroupMembership, GroupPermission
from students.services import _require_permission, get_group

from .models import SubmissionLink, Task, TaskComment, TaskProgress

EDITABLE_FIELDS = frozenset(
    {"title", "topic", "subject", "starts_on", "deadline", "is_required", "description", "work_type", "priority"}
)


def _save_task(task):
    for field in ("title", "description"):
        value = getattr(task, field)
        if isinstance(value, str):
            setattr(task, field, value.strip())
    task.full_clean()
    if isinstance(task.deadline, datetime) and timezone.is_naive(task.deadline):
        raise ValidationError({"deadline": "Дедлайн повинен містити часовий пояс."})
    task.save()
    return task


def _replace_links(task, urls):
    if not isinstance(urls, (list, tuple)):
        raise ValidationError({"submission_links": "Передайте список посилань."})
    links = []
    seen = set()
    for url in urls:
        link = SubmissionLink(task=task, url=url.strip() if isinstance(url, str) else url)
        link.full_clean(validate_unique=False, validate_constraints=False)
        if link.url in seen:
            raise ValidationError({"submission_links": "Посилання не повинні повторюватися."})
        seen.add(link.url)
        links.append(link)
    task.submission_links.all().delete()
    SubmissionLink.objects.bulk_create(links)


@transaction.atomic
def create_task(
    *,
    title,
    subject,
    deadline,
    topic=None,
    starts_on=None,
    is_required=True,
    description="",
    submission_links=(),
    work_type=Task.WorkType.INDEPENDENT,
    priority=Task.Priority.NORMAL,
    created_by=None,
):
    task = _save_task(
        Task(
            title=title,
            topic=topic,
            subject=subject,
            deadline=deadline,
            starts_on=starts_on,
            is_required=is_required,
            description=description,
            work_type=work_type,
            priority=priority,
            created_by=created_by,
        )
    )
    _replace_links(task, submission_links)
    return task


@transaction.atomic
def update_task(task_id, *, submission_links=None, **changes):
    """Update supplied fields; None keeps links, an empty list clears them."""
    unknown = changes.keys() - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(dict.fromkeys(unknown, "Це поле не можна змінювати."))
    task = Task.objects.select_for_update().get(pk=task_id)
    for field, value in changes.items():
        setattr(task, field, value)
    _save_task(task)
    if submission_links is not None:
        _replace_links(task, submission_links)
    return task


def get_task(task_id):
    return Task.objects.prefetch_related("submission_links").get(pk=task_id)


def list_tasks(*, subject=None, is_required=None, deadline_from=None, deadline_to=None):
    """Return tasks by deadline, with inclusive deadline boundaries."""
    tasks = Task.objects.prefetch_related("submission_links")
    if subject is not None:
        tasks = (
            tasks.filter(subject__name__iexact=subject.strip())
            if isinstance(subject, str)
            else tasks.filter(subject=subject)
        )
    if is_required is not None:
        tasks = tasks.filter(is_required=is_required)
    if deadline_from is not None:
        tasks = tasks.filter(deadline__gte=deadline_from)
    if deadline_to is not None:
        tasks = tasks.filter(deadline__lte=deadline_to)
    return tasks


def delete_task(task_id):
    get_task(task_id).delete()


@transaction.atomic
def create_group_task(user, **fields):
    """Authorized entry point for future views; create_task is low-level CRUD."""
    subject = fields["subject"]
    _require_permission(user, subject.group, GroupPermission.MANAGE_TASKS)
    return create_task(created_by=user, **fields)


@transaction.atomic
def set_task_status(user, task_id, *, status):
    task = Task.objects.select_related("subject__semester__group").get(pk=task_id)
    if task.group is None:
        raise PermissionDenied("Спочатку прив'яжіть завдання до навчального плану.")
    get_group(user, task.group.pk)
    # Serialize competing status changes for the same student and task.
    GroupMembership.objects.select_for_update().get(user=user, group=task.group)
    progress, _ = TaskProgress.objects.get_or_create(task=task, user=user)
    progress.status = status
    progress.full_clean()
    progress.save()
    return progress


@transaction.atomic
def add_comment(user, task_id, *, body, mentioned_user_ids=()):
    task = Task.objects.select_related("subject__semester__group").get(pk=task_id)
    if task.group is None:
        raise PermissionDenied
    group = get_group(user, task.group.pk)
    mentions = set(mentioned_user_ids)
    members = set(group.memberships.filter(user_id__in=mentions).values_list("user_id", flat=True))
    if members != mentions:
        raise ValidationError("Згадувати можна лише учасників групи завдання.")
    comment = TaskComment(task=task, author=user, body=body.strip())
    comment.full_clean()
    comment.save()
    comment.mentions.set(members)
    return comment
