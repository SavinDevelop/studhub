from django.db.models import CharField, Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from tasks.models import Task, TaskProgress

DONE = (TaskProgress.Status.COMPLETED, TaskProgress.Status.GRADED)


def visible_tasks(user):
    status = TaskProgress.objects.filter(task_id=OuterRef("pk"), user=user).values("status")[:1]
    return (
        Task.objects.filter(subject__semester__group__memberships__user=user)
        .select_related("subject__semester__group", "topic")
        .annotate(
            personal_status=Coalesce(Subquery(status), Value(TaskProgress.Status.NOT_STARTED), output_field=CharField())
        )
    )


def semester_tasks(user, workspace):
    tasks = visible_tasks(user)
    return tasks.filter(subject__semester=workspace["semester"]) if workspace["semester"] else tasks.none()


def task_stats(tasks):
    return tasks.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=~Q(personal_status__in=DONE)),
        completed=Count("pk", filter=Q(personal_status__in=DONE)),
        graded=Count("pk", filter=Q(personal_status=TaskProgress.Status.GRADED)),
        in_progress=Count("pk", filter=Q(personal_status=TaskProgress.Status.IN_PROGRESS)),
        overdue=Count("pk", filter=Q(deadline__lt=timezone.now()) & ~Q(personal_status__in=DONE)),
        required=Count("pk", filter=Q(is_required=True)),
        required_done=Count("pk", filter=Q(is_required=True, personal_status__in=DONE)),
    )


def percent(done, total):
    return round(done * 100 / total) if total else 0
