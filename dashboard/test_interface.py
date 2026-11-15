from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from academics.models import Semester, Subject
from notifications.models import Notification
from students.models import GroupMembership
from students.profiles import complete_profile
from students.services import create_group
from tasks.models import Task, TaskProgress

pytestmark = pytest.mark.django_db


@pytest.fixture
def ui_data(django_user_model):
    owner = django_user_model.objects.create_user(username="ui_owner", email="owner@example.com")
    member = django_user_model.objects.create_user(username="ui_member", email="member@example.com")
    outsider = django_user_model.objects.create_user(username="ui_outsider", email="outsider@example.com")
    for user in (owner, member, outsider):
        complete_profile(user, first_name="Олена", last_name=user.username)
    group = create_group(owner, name="КН-21")
    GroupMembership.objects.create(user=member, group=group)
    semester = Semester.objects.create(
        group=group,
        name="Осінній семестр",
        academic_year_start=2026,
        starts_on=date(2026, 9, 1),
        ends_on=date(2026, 12, 31),
        is_active=True,
    )
    archive = Semester.objects.create(
        group=group,
        name="Архівний семестр",
        academic_year_start=2025,
        starts_on=date(2026, 2, 1),
        ends_on=date(2026, 5, 31),
    )
    subject = Subject.objects.create(semester=semester, name="Алгоритми", teacher_name="Викладач")
    old_subject = Subject.objects.create(semester=archive, name="Архівний предмет", teacher_name="Викладач")
    task = Task.objects.create(subject=subject, title="Поточне завдання", deadline=timezone.now() + timedelta(days=1))
    old_task = Task.objects.create(
        subject=old_subject, title="Архівне завдання", deadline=timezone.now() - timedelta(days=60)
    )
    return {
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "group": group,
        "semester": semester,
        "archive": archive,
        "subject": subject,
        "task": task,
        "old_task": old_task,
    }


@pytest.mark.parametrize(
    "route",
    [
        "students:dashboard",
        "students:groups",
        "tasks:list",
        "tasks:table",
        "tasks:create",
        "tasks:calendar",
        "academics:subjects",
        "academics:subject_create",
        "academics:semesters",
        "academics:semester_create",
        "dashboard:analytics",
        "dashboard:matrix",
        "notifications:inbox",
        "students:account_settings",
    ],
)
def test_interface_pages_render_with_real_data(client, ui_data, route):
    client.force_login(ui_data["owner"])
    response = client.get(reverse(route))
    assert response.status_code == 200
    assert "data-sidebar-toggle" in response.content.decode()
    assert "api/mcp/asset" not in response.content.decode()


@pytest.mark.parametrize(
    ("route", "key"),
    [
        ("tasks:detail", "task"),
        ("tasks:edit", "task"),
        ("academics:subject_edit", "subject"),
        ("academics:semester_edit", "semester"),
        ("students:group", "group"),
        ("students:invitations", "group"),
        ("academics:curriculum", "group"),
    ],
)
def test_detail_and_editor_pages_render(client, ui_data, route, key):
    client.force_login(ui_data["owner"])
    assert client.get(reverse(route, args=[ui_data[key].pk])).status_code == 200


def test_semester_and_status_filters_preserve_personal_progress(client, ui_data):
    owner, member, task = ui_data["owner"], ui_data["member"], ui_data["task"]
    TaskProgress.objects.create(user=owner, task=task, status="graded")
    client.force_login(member)
    response = client.get(reverse("tasks:list"))
    assert next(iter(response.context["page"])).personal_status == "not_started"
    assert ui_data["old_task"] not in list(response.context["page"])
    response = client.get(reverse("tasks:list"), {"semester": ui_data["archive"].pk})
    assert list(response.context["page"]) == [ui_data["old_task"]]
    assert not client.get(reverse("tasks:list"), {"status": "graded"}).context["page"]
    client.post(reverse("tasks:status", args=[task.pk]), {"status": "completed"})
    assert TaskProgress.objects.get(user=owner, task=task).status == "graded"
    assert TaskProgress.objects.get(user=member, task=task).status == "completed"


def test_outsiders_cannot_read_or_change_tasks(client, ui_data):
    client.force_login(ui_data["outsider"])
    task = ui_data["task"]
    for route in ("tasks:detail", "tasks:edit"):
        assert client.get(reverse(route, args=[task.pk])).status_code == 404
    for route in ("tasks:status", "tasks:comment", "tasks:delete"):
        assert client.post(reverse(route, args=[task.pk]), {"status": "graded", "body": "bad"}).status_code == 404
    assert not task.progress.exists()
    assert not task.comments.exists()


def test_member_cannot_edit_curriculum_or_view_group_matrix(client, ui_data):
    client.force_login(ui_data["member"])
    assert client.get(reverse("tasks:edit", args=[ui_data["task"].pk])).status_code == 403
    assert client.get(reverse("academics:subject_edit", args=[ui_data["subject"].pk])).status_code == 403
    assert client.get(reverse("dashboard:matrix")).status_code == 403
    assert client.get(reverse("dashboard:analytics"), {"export": "csv"}).status_code == 403


def test_create_task_upload_and_comment_flow(client, ui_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": "Нове завдання",
            "subject": ui_data["subject"].pk,
            "work_type": "independent",
            "priority": "high",
            "deadline": (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "is_required": "on",
            "description": "Опис",
            "submission_urls": "https://example.com/submit",
            "attachment": SimpleUploadedFile("guide.txt", b"material"),
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title="Нове завдання")
    assert task.created_by == ui_data["owner"]
    attachment = task.attachments.get()
    client.force_login(ui_data["member"])
    response = client.get(reverse("tasks:attachment", args=[task.pk, attachment.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"material"
    assert client.get(attachment.file.url).status_code == 404
    response = client.post(reverse("tasks:comment", args=[task.pk]), {"body": "  Дякую!  "})
    assert response.status_code == 302
    assert task.comments.get().body == "Дякую!"
    assert Notification.objects.filter(recipient=ui_data["member"], task=task).exists()
    client.force_login(ui_data["outsider"])
    assert client.get(reverse("tasks:attachment", args=[task.pk, attachment.pk])).status_code == 404


def test_forged_subject_cannot_create_task_in_another_group(client, ui_data):
    client.force_login(ui_data["outsider"])
    create_group(ui_data["outsider"], name="Інша група")
    response = client.post(
        reverse("tasks:create"),
        {
            "title": "Підробка",
            "subject": ui_data["subject"].pk,
            "deadline": "2027-01-01T12:00",
            "work_type": "independent",
            "priority": "normal",
        },
    )
    assert response.status_code == 200
    assert response.context["form"].errors
    assert not Task.objects.filter(title="Підробка").exists()


def test_state_changes_require_post_and_csrf(ui_data):
    client = Client(enforce_csrf_checks=True)
    client.force_login(ui_data["owner"])
    task = ui_data["task"]
    for route in ("tasks:status", "tasks:comment", "tasks:delete"):
        url = reverse(route, args=[task.pk])
        assert client.get(url).status_code == 405
        assert client.post(url, {}).status_code == 403


def test_notifications_are_private_and_post_marks_read(client, ui_data):
    notice = Notification.objects.create(
        recipient=ui_data["owner"],
        group=ui_data["group"],
        task=ui_data["task"],
        kind="task_created",
        title="Для старости",
    )
    client.force_login(ui_data["member"])
    assert "Для старости" not in client.get(reverse("notifications:inbox")).content.decode()
    assert client.post(reverse("notifications:read", args=[notice.pk])).status_code == 404
    notice.refresh_from_db()
    assert notice.read_at is None
    client.force_login(ui_data["owner"])
    assert client.post(reverse("notifications:read", args=[notice.pk])).status_code == 302
    notice.refresh_from_db()
    assert notice.read_at is not None


def test_quick_status_returns_to_table_and_persists(client, ui_data):
    client.force_login(ui_data["member"])
    response = client.post(
        reverse("tasks:status", args=[ui_data["task"].pk]), {"status": "in_progress", "return": "table"}
    )
    assert response.url == reverse("tasks:table")
    assert TaskProgress.objects.get(task=ui_data["task"], user=ui_data["member"]).status == "in_progress"


def test_semester_selection_persists_when_navigating(client, ui_data):
    client.force_login(ui_data["owner"])
    client.get(reverse("academics:subjects"), {"semester": ui_data["archive"].pk})
    response = client.get(reverse("tasks:list"))
    assert list(response.context["page"]) == [ui_data["old_task"]]


def test_topics_can_only_be_added_by_authorized_members(client, ui_data):
    client.force_login(ui_data["member"])
    url = reverse("academics:topic_create", args=[ui_data["subject"].pk])
    assert client.post(url, {"name": "Нова тема"}).status_code == 403
    client.force_login(ui_data["owner"])
    assert client.post(url, {"name": "Нова тема"}).status_code == 302
    assert ui_data["subject"].topics.get().name == "Нова тема"


@pytest.mark.parametrize(
    "route", ["students:group", "students:group_settings", "students:group_permissions", "academics:curriculum"]
)
def test_group_sections_are_separate_pages_with_active_sidebar_links(client, ui_data, route):
    client.force_login(ui_data["owner"])
    response = client.get(reverse(route, args=[ui_data["group"].pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert '<nav class="tabs' not in body
    assert body.count('aria-current="page"') == 1
    assert {item["key"] for item in response.context["workspace"]["group_nav"]} == {
        "members",
        "curriculum",
        "semesters",
        "settings",
        "permissions",
        "invitations",
        "matrix",
    }
    if route == "students:group":
        assert 'id="permissions"' not in body
        assert 'id="general"' not in body
    if route == "students:group_settings":
        assert 'name="name"' in body
        assert 'name="can_manage_tasks"' not in body
    if route == "students:group_permissions":
        assert 'name="can_manage_tasks"' in body
        assert 'id="members"' not in body


@pytest.mark.parametrize("role", ["student", "deputy"])
def test_group_navigation_does_not_expose_owner_only_pages(client, ui_data, role):
    member = ui_data["member"]
    GroupMembership.objects.filter(user=member, group=ui_data["group"]).update(role=role)
    client.force_login(member)
    response = client.get(reverse("students:group", args=[ui_data["group"].pk]))
    keys = {item["key"] for item in response.context["workspace"]["group_nav"]}
    assert keys == ({"members", "curriculum", "semesters", "invitations"} if role == "deputy" else {"members"})
    for route in ("students:group_settings", "students:group_permissions"):
        assert client.get(reverse(route, args=[ui_data["group"].pk])).status_code == 403


def test_group_settings_page_saves_name_and_preserves_invalid_form(client, ui_data):
    client.force_login(ui_data["owner"])
    group = ui_data["group"]
    url = reverse("students:group_settings", args=[group.pk])
    response = client.post(url, {"name": "Нова назва"})
    assert response.status_code == 302
    assert response.url == url
    group.refresh_from_db()
    assert group.name == "Нова назва"
    response = client.post(url, {"name": " "})
    assert response.status_code == 200
    assert response.context["form"].errors
    group.refresh_from_db()
    assert group.name == "Нова назва"


def test_role_permissions_form_returns_to_its_own_page(client, ui_data):
    client.force_login(ui_data["owner"])
    group = ui_data["group"]
    response = client.post(
        reverse("students:role_permissions", args=[group.pk, "student"]), {"return": "permissions", "can_invite": "on"}
    )
    assert response.url == reverse("students:group_permissions", args=[group.pk])
    assert group.role_policies.get(role="student").can_invite


def test_new_group_pages_reject_outsiders_and_require_csrf(ui_data):
    client = Client(enforce_csrf_checks=True)
    client.force_login(ui_data["outsider"])
    for route in ("students:group_settings", "students:group_permissions"):
        assert client.get(reverse(route, args=[ui_data["group"].pk])).status_code == 403
    client.force_login(ui_data["owner"])
    assert (
        client.post(reverse("students:group_settings", args=[ui_data["group"].pk]), {"name": "Підробка"}).status_code
        == 403
    )
