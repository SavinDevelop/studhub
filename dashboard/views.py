import csv
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from students.models import GroupPermission
from students.services import _require_permission
from tasks.models import TaskProgress

from .selectors import DONE, percent, semester_tasks
from .workspace import workspace_for


@login_required
def analytics(request, matrix=False):
    workspace = workspace_for(request)
    group = workspace["group"]
    if group is None:
        return render(request, "students/dashboard.html", {"nav": "overview", "page_title": "Мій огляд"})
    _require_permission(request.user, group, GroupPermission.VIEW_ANALYTICS)
    tasks = list(semester_tasks(request.user, workspace))
    if matrix:
        tasks.sort(key=lambda task: (task.subject.name, task.deadline, task.pk))
    if request.GET.get("subject", "").isdecimal():
        tasks = [task for task in tasks if task.subject_id == int(request.GET["subject"])]
    members = list(group.memberships.select_related("user__student_profile"))
    if request.GET.get("member", "").isdecimal():
        members = [member for member in members if member.user_id == int(request.GET["member"])]
    task_ids = [task.pk for task in tasks]
    progress = {(item.user_id, item.task_id): item.status for item in TaskProgress.objects.filter(task_id__in=task_ids)}
    rows = []
    for member in members:
        states = [progress.get((member.user_id, task.pk), TaskProgress.Status.NOT_STARTED) for task in tasks]
        rows.append(
            {
                "member": member,
                "cells": list(zip(tasks, states, strict=True)),
                "percent": percent(sum(state in DONE for state in states), len(tasks)),
                "graded": states.count(TaskProgress.Status.GRADED),
            }
        )
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="studhub-progress.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)

        def safe_cell(value):
            text = str(value)
            return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

        writer.writerow(["Учасник", *[safe_cell(task.title) for task in tasks]])
        for row in rows:
            writer.writerow(
                [
                    safe_cell(row["member"].user.student_profile),
                    *[dict(TaskProgress.Status.choices)[state] for _, state in row["cells"]],
                ]
            )
        return response
    subject_rows = []
    grouped = defaultdict(list)
    for task in tasks:
        grouped[task.subject].append(task)
    for subject, subject_tasks in grouped.items():
        states = [
            progress.get((member.user_id, task.pk), "not_started") for member in members for task in subject_tasks
        ]
        subject_rows.append(
            {
                "subject": subject,
                "tasks": subject_tasks,
                "percent": percent(sum(state in DONE for state in states), len(states)),
            }
        )
    all_states = [state for row in rows for _, state in row["cells"]]
    stats = {
        "total": len(tasks),
        "percent": percent(sum(state in DONE for state in all_states), len(all_states)),
        "graded_percent": percent(all_states.count("graded"), len(all_states)),
        "overdue": sum(task.is_overdue and state not in DONE for row in rows for task, state in row["cells"]),
    }
    stats["overdue_percent"] = percent(stats["overdue"], len(all_states))
    return render(
        request,
        "dashboard/matrix.html" if matrix else "dashboard/analytics.html",
        {
            "rows": rows,
            "tasks": tasks,
            "subject_rows": subject_rows,
            "stats": stats,
            "members": group.memberships.select_related("user__student_profile"),
            "subjects": workspace["semester"].subjects.all() if workspace["semester"] else [],
            "page_title": "Матриця виконання групи" if matrix else "Аналітика групи",
            "nav": "matrix" if matrix else "analytics",
        },
    )
