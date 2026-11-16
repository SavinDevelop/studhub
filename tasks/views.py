import calendar as month_calendar
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from academics.models import Topic
from dashboard.selectors import semester_tasks, visible_tasks
from dashboard.workspace import workspace_for
from notifications.models import Notification
from students.models import GroupPermission
from students.services import _require_permission

from . import services
from .forms import TaskForm
from .models import Task, TaskAttachment, TaskProgress


def _task(request, pk):
    task = get_object_or_404(visible_tasks(request.user), pk=pk)
    request.session["active_group"] = task.group.pk
    return task


def _filtered_tasks(request):
    workspace = workspace_for(request)
    tasks = (
        visible_tasks(request.user) if request.GET.get("scope") == "all" else semester_tasks(request.user, workspace)
    )
    search = request.GET.get("q", "").strip()
    if search:
        tasks = tasks.filter(
            Q(title__icontains=search) | Q(subject__name__icontains=search) | Q(description__icontains=search)
        )
    status = request.GET.get("status", "")
    if status in TaskProgress.Status.values:
        tasks = tasks.filter(personal_status=status)
    subject = request.GET.get("subject", "")
    if subject:
        if not subject.isdecimal():
            raise Http404
        tasks = tasks.filter(subject_id=subject)
    if request.GET.get("priority") in Task.Priority.values:
        tasks = tasks.filter(priority=request.GET["priority"])
    if request.GET.get("required") == "1":
        tasks = tasks.filter(is_required=True)
    if request.GET.get("overdue") == "1":
        tasks = tasks.filter(deadline__lt=timezone.now()).exclude(personal_status__in=("completed", "graded"))
    order = request.GET.get("sort", "deadline")
    return tasks.order_by("-deadline" if order == "-deadline" else "deadline", "pk")


@login_required
def task_list(request, table=False):
    if table:
        params = request.GET.copy()
        params["view"] = "table"
        return redirect(reverse("tasks:list") + "?" + params.urlencode())
    table = request.GET.get("view") == "table"
    workspace = workspace_for(request)
    tasks = _filtered_tasks(request)
    subjects = workspace["semester"].subjects.all() if workspace["semester"] else []
    page = Paginator(tasks, 4).get_page(request.GET.get("page"))
    return render(
        request,
        "tasks/list.html",
        {
            "page": page,
            "subjects": subjects,
            "statuses": TaskProgress.Status.choices,
            "priorities": Task.Priority.choices,
            "table_mode": table,
            "nav": "tasks",
            "page_title": "Завдання",
        },
    )


@login_required
def task_detail(request, pk):
    task = _task(request, pk)
    return render(
        request,
        "tasks/detail.html",
        {
            "task": task,
            "comments": task.comments.select_related("author__student_profile"),
            "statuses": TaskProgress.Status.choices,
            "can_edit": _can_manage(request.user, task.group),
            "nav": "tasks",
            "page_title": "Мої завдання",
        },
    )


def _can_manage(user, group):
    from students.services import has_group_permission

    return has_group_permission(user, group, GroupPermission.MANAGE_TASKS)


@login_required
@transaction.atomic
def task_editor(request, pk=None):
    task = _task(request, pk) if pk else None
    group = task.group if task else workspace_for(request)["group"]
    if group is None:
        messages.info(request, "Спочатку створіть групу та навчальний план.")
        return redirect("students:groups")
    _require_permission(request.user, group, GroupPermission.MANAGE_TASKS)
    form = TaskForm(request.POST or None, request.FILES or None, group=group, instance=task)
    if request.method == "POST" and form.is_valid():
        fields = {key: form.cleaned_data[key] for key in form.Meta.fields}
        try:
            with transaction.atomic():
                name = form.cleaned_data["topic_name"]
                fields["topic"] = Topic.objects.get_or_create(subject=fields["subject"], name=name)[0] if name else None
                if task:
                    task = services.update_task(
                        task.pk, submission_links=form.cleaned_data["submission_urls"], **fields
                    )
                else:
                    task = services.create_group_task(
                        request.user, submission_links=form.cleaned_data["submission_urls"], **fields
                    )
                for upload in form.cleaned_data["attachment"]:
                    TaskAttachment.objects.create(
                        task=task, name=upload.name[:255], file=upload, uploaded_by=request.user
                    )
                urls = form.cleaned_data["attachment_url"]
                task.attachments.exclude(url="").exclude(url__in=urls).delete()
                for url in urls:
                    if not task.attachments.filter(url=url).exists():
                        TaskAttachment.objects.create(
                            task=task,
                            name="Матеріали до завдання",
                            url=url,
                            uploaded_by=request.user,
                        )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            kind = Notification.Kind.TASK_UPDATED if pk else Notification.Kind.TASK_CREATED
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=membership.user_id,
                        group=group,
                        task=task,
                        kind=kind,
                        title="Оновлено завдання" if pk else "Нове завдання у групі",
                        body=task.title,
                    )
                    for membership in group.memberships.exclude(user=request.user)
                ]
            )
            messages.success(request, "Завдання збережено.")
            return redirect("tasks:detail", pk=task.pk)
    return render(
        request,
        "tasks/editor.html",
        {
            "form": form,
            "task": task,
            "nav": "tasks",
            "page_title": "Редагування завдання" if task else "Нове завдання",
        },
    )


@login_required
@require_POST
def task_status(request, pk):
    task = _task(request, pk)
    try:
        services.set_task_status(request.user, task.pk, status=request.POST.get("status"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Статус завдання оновлено.")
    if request.POST.get("return") in {"list", "table"}:
        params = QueryDict(request.POST.get("return_query", "")).copy()
        if request.POST["return"] == "table":
            params["view"] = "table"
        else:
            params.pop("view", None)
        query = params.urlencode()
        return redirect(reverse("tasks:list") + ("?" + query if query else ""))
    return redirect("tasks:detail", pk=task.pk)


@login_required
@require_POST
def task_comment(request, pk):
    task = _task(request, pk)
    try:
        services.add_comment(request.user, task.pk, body=request.POST.get("body", ""))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(reverse("tasks:detail", args=[pk]) + "#discussion")


@login_required
@require_POST
def task_delete(request, pk):
    task = _task(request, pk)
    _require_permission(request.user, task.group, GroupPermission.MANAGE_TASKS)
    task.delete()
    messages.success(request, "Завдання видалено.")
    return redirect("tasks:list")


@login_required
def attachment(request, pk, attachment_id):
    task = _task(request, pk)
    item = get_object_or_404(TaskAttachment, pk=attachment_id, task=task)
    if item.url:
        return redirect(item.url)
    if not item.file:
        raise Http404
    return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.name)


@login_required
def calendar(request):
    today = timezone.localdate()
    try:
        month = date.fromisoformat(request.GET.get("month", today.strftime("%Y-%m")) + "-01")
        previous = (month - timedelta(days=1)).replace(day=1)
        following = (month + timedelta(days=32)).replace(day=1)
    except (ValueError, OverflowError) as exc:
        raise Http404 from exc
    events = defaultdict(list)
    for task in visible_tasks(request.user).filter(deadline__date__gte=month, deadline__date__lt=following):
        events[timezone.localtime(task.deadline).date()].append(task)
    weeks = [
        [
            {"day": day, "events": events[day], "current": day.month == month.month, "today": day == today}
            for day in week
        ]
        for week in month_calendar.Calendar().monthdatescalendar(month.year, month.month)
    ]
    return render(
        request,
        "tasks/calendar.html",
        {
            "weeks": weeks,
            "weekdays": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
            "month": month,
            "previous": previous,
            "following": following,
            "nav": "calendar",
            "page_title": "Календар",
        },
    )
