"""Shared workspace selection and authorization for server-rendered screens."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse

from academics.models import Semester
from students.models import GroupPermission
from students.services import has_group_permission


def workspace_for(request):
    if hasattr(request, "studhub_workspace"):
        return request.studhub_workspace
    if not request.user.is_authenticated:
        return {}
    memberships = list(request.user.group_memberships.select_related("group", "user__student_profile"))
    requested = request.resolver_match.kwargs.get("group_id") if request.resolver_match else None
    requested = requested or request.GET.get("group")
    explicit = requested is not None
    requested = requested or request.session.get("active_group")
    if requested is not None:
        try:
            requested = int(requested)
        except (TypeError, ValueError) as exc:
            raise Http404 from exc
    membership = next((item for item in memberships if item.group_id == requested), None)
    if explicit and membership is None:
        raise PermissionDenied
    membership = membership or (memberships[0] if memberships else None)
    group = membership.group if membership else None
    if group:
        request.session["active_group"] = group.pk
    semesters = list(Semester.objects.filter(group=group)) if group else []
    saved_semesters = request.session.get("active_semesters", {})
    semester_id = request.GET.get("semester")
    semester = None
    if semester_id is None and group:
        saved = saved_semesters.get(str(group.pk))
        semester = next((item for item in semesters if str(item.pk) == str(saved)), None)
    if semester_id:
        semester = next((item for item in semesters if str(item.pk) == semester_id), None)
        if semester is None:
            raise Http404
    elif semester is None:
        semester = next((item for item in semesters if item.is_active), None)
        semester = semester or (semesters[0] if semesters else None)
    if semester and group:
        saved_semesters[str(group.pk)] = semester.pk
        request.session["active_semesters"] = saved_semesters
    permissions = {
        permission.value: bool(group and has_group_permission(request.user, group, permission))
        for permission in GroupPermission
    }
    role = (
        "Староста"
        if group and group.owner_id == request.user.pk
        else membership.get_role_display()
        if membership
        else "Студент"
    )
    nav = [
        ("overview", "Огляд", "students:dashboard", "overview"),
        ("tasks", "Завдання", "tasks:list", "tasks"),
        ("calendar", "Календар", "tasks:calendar", "calendar"),
        ("subjects", "Предмети", "academics:subjects", "subjects"),
    ]
    group_nav = []
    if group:
        group_nav.append(
            {"key": "members", "label": "Учасники", "url": reverse("students:group", args=[group.pk]), "icon": "users"}
        )
        if permissions[GroupPermission.MANAGE_ACADEMICS]:
            group_nav.extend(
                [
                    {
                        "key": "curriculum",
                        "label": "Навчальний план",
                        "url": reverse("academics:curriculum", args=[group.pk]),
                        "icon": "subjects",
                    },
                ]
            )
        if permissions[GroupPermission.EDIT_GROUP]:
            group_nav.append(
                {
                    "key": "settings",
                    "label": "Налаштування групи",
                    "url": reverse("students:group_settings", args=[group.pk]),
                    "icon": "settings",
                }
            )
        if group.owner_id == request.user.pk:
            group_nav.append(
                {
                    "key": "permissions",
                    "label": "Дозволи",
                    "url": reverse("students:group_permissions", args=[group.pk]),
                    "icon": "users",
                }
            )
        if permissions[GroupPermission.INVITE]:
            group_nav.append(
                {
                    "key": "invitations",
                    "label": "Запрошення",
                    "url": reverse("students:invitations", args=[group.pk]),
                    "icon": "mail",
                }
            )
        if permissions[GroupPermission.VIEW_ANALYTICS]:
            group_nav.append(
                {"key": "analytics", "label": "Аналітика", "url": reverse("dashboard:analytics"), "icon": "analytics"}
            )
            group_nav.append(
                {"key": "matrix", "label": "Матриця виконання", "url": reverse("dashboard:matrix"), "icon": "analytics"}
            )
    request.studhub_workspace = {
        "group": group,
        "memberships": memberships,
        "group_nav": group_nav,
        "membership": membership,
        "semesters": semesters,
        "active_semester": next((item for item in semesters if item.is_active), None),
        "semester": semester,
        "role": role,
        "permissions": permissions,
        "is_owner": bool(group and group.owner_id == request.user.pk),
        "unread": request.user.notifications.filter(read_at__isnull=True).count(),
        "nav": [{"key": key, "label": label, "url": reverse(url), "icon": icon} for key, label, url, icon in nav],
    }
    return request.studhub_workspace


def workspace_context(request):
    return {"workspace": workspace_for(request)}
