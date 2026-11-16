from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from dashboard.selectors import percent, semester_tasks
from dashboard.workspace import workspace_for
from students.models import GroupPermission
from students.services import _require_permission, get_group

from . import services
from .forms import CourseForm, SemesterForm, SubjectForm
from .models import Semester, Subject


def _subjects(request):
    workspace = workspace_for(request)
    return (
        Subject.objects.filter(semester=workspace["semester"]).annotate(task_count=Count("tasks"))
        if workspace["semester"]
        else Subject.objects.none()
    )


@login_required
def subjects(request):
    items = _subjects(request)
    state = request.GET.get("state", "all")
    if state in ("active", "archive"):
        items = items.filter(is_archived=state == "archive")
    tasks = list(semester_tasks(request.user, workspace_for(request)))
    for subject in items:
        personal = [task for task in tasks if task.subject_id == subject.pk]
        subject.percent = percent(
            sum(task.personal_status in ("completed", "graded") for task in personal), len(personal)
        )
    return render(
        request,
        "academics/subjects.html",
        {"subjects": items, "state": state, "page_title": "Предмети", "nav": "subjects"},
    )


@login_required
def curriculum(request, group_id):
    group = get_group(request.user, group_id)
    _require_permission(request.user, group, GroupPermission.MANAGE_ACADEMICS)
    form = CourseForm(initial={"course": group.course})
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            services.update_course(request.user, group.pk, **form.cleaned_data)
            messages.success(request, "Курс навчання оновлено.")
            return redirect("academics:curriculum", group_id=group.pk)
    return render(
        request,
        "academics/curriculum.html",
        {
            "subjects": _subjects(request),
            "semesters": group.semesters.annotate(subject_count=Count("subjects")),
            "course_form": form,
            "nav": "curriculum",
            "page_title": "Навчальний план",
        },
    )


@login_required
def subject_editor(request, pk=None):
    instance = (
        get_object_or_404(
            Subject.objects.select_related("semester__group"), pk=pk, semester__group__memberships__user=request.user
        )
        if pk
        else None
    )
    group = instance.group if instance else workspace_for(request)["group"]
    if group is None:
        return redirect("students:groups")
    _require_permission(request.user, group, GroupPermission.MANAGE_ACADEMICS)
    form = SubjectForm(
        request.POST or None,
        instance=instance,
        group=group,
        initial={"semester": workspace_for(request)["semester"]} if not pk else None,
    )
    if request.method == "POST" and form.is_valid():
        fields = form.cleaned_data.copy()
        try:
            if instance:
                services.update_subject(request.user, instance.pk, **fields)
            else:
                semester = fields.pop("semester")
                services.create_subject(request.user, semester.pk, **fields)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Предмет збережено.")
            return redirect("academics:curriculum", group_id=group.pk)
    return render(
        request,
        "academics/subject_form.html",
        {
            "form": form,
            "subject": instance,
            "page_title": "Редагувати предмет" if pk else "Новий предмет",
            "nav": "curriculum",
        },
    )


@login_required
def semesters(request):
    workspace = workspace_for(request)
    if workspace["group"] is None:
        return redirect("students:groups")
    _require_permission(request.user, workspace["group"], GroupPermission.MANAGE_ACADEMICS)
    return redirect("academics:curriculum", group_id=workspace["group"].pk)


@login_required
def semester_editor(request, pk=None):
    workspace = workspace_for(request)
    group = workspace["group"]
    if group is None:
        return redirect("students:groups")
    _require_permission(request.user, group, GroupPermission.MANAGE_ACADEMICS)
    instance = get_object_or_404(Semester, pk=pk, group=group) if pk else Semester(group=group)
    form = SemesterForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            if pk:
                services.update_semester(request.user, pk, **form.cleaned_data)
            else:
                services.create_semester(
                    request.user,
                    group.pk,
                    is_active=not group.semesters.filter(is_active=True).exists(),
                    **form.cleaned_data,
                )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Семестр збережено.")
            return redirect("academics:curriculum", group_id=group.pk)
    return render(
        request,
        "academics/semester_form.html",
        {"form": form, "nav": "curriculum", "page_title": "Редагувати період" if pk else "Новий семестр"},
    )


@login_required
@require_POST
def activate(request, pk):
    group = workspace_for(request)["group"]
    semester = get_object_or_404(Semester, pk=pk, group=group)
    services.activate_semester(request.user, semester.pk)
    messages.success(request, "Активний семестр змінено.")
    return redirect("academics:curriculum", group_id=group.pk)


@login_required
@require_POST
def topic_create(request, pk):
    from .forms import TopicForm

    subject = get_object_or_404(
        Subject.objects.select_related("semester__group"), pk=pk, semester__group__memberships__user=request.user
    )
    _require_permission(request.user, subject.group, GroupPermission.MANAGE_ACADEMICS)
    form = TopicForm(request.POST)
    if form.is_valid():
        try:
            services.create_topic(
                request.user, subject.pk, name=form.cleaned_data["name"], position=subject.topics.count()
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, "Тему додано.")
    else:
        messages.error(request, "Вкажіть назву теми до 255 символів.")
    return redirect("academics:subject_edit", pk=pk)
