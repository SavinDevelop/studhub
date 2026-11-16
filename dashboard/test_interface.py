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
        "tasks:create",
        "tasks:calendar",
        "academics:subjects",
        "academics:subject_create",
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
    assert response.url == reverse("tasks:list") + "?view=table"
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
        "settings",
        "permissions",
        "invitations",
        "analytics",
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
    assert keys == ({"members", "curriculum", "invitations"} if role == "deputy" else {"members"})
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


@pytest.mark.parametrize("mode", ["list", "table"])
def test_task_display_modes_share_navigation_and_keep_filters(client, ui_data, mode):
    client.force_login(ui_data["owner"])
    params = {"q": ui_data["task"].title, "status": "not_started", "sort": "-deadline"}
    if mode == "table":
        params["view"] = "table"
    response = client.get(reverse("tasks:list"), params)
    assert response.status_code == 200
    assert response.context["table_mode"] == (mode == "table")
    assert response.context["nav"] == "tasks"
    assert response.context["page_title"] == "Завдання"
    assert "table" not in {item["key"] for item in response.context["workspace"]["nav"]}
    assert ui_data["task"] in response.context["page"]
    assert 'aria-label="Вигляд завдань"' in response.content.decode()


def test_old_table_url_redirects_to_unified_tasks_with_filters(client, ui_data):
    client.force_login(ui_data["owner"])
    response = client.get(reverse("tasks:table"), {"status": "completed", "q": "test"})
    assert response.status_code == 302
    assert response.url == reverse("tasks:list") + "?status=completed&q=test&view=table"


def test_quick_status_keeps_task_view_and_filters(client, ui_data):
    client.force_login(ui_data["member"])
    response = client.post(
        reverse("tasks:status", args=[ui_data["task"].pk]),
        {
            "status": "in_progress",
            "return": "table",
            "return_query": "view=table&q=test&sort=-deadline&page=2",
        },
    )
    assert response.url == reverse("tasks:list") + "?view=table&q=test&sort=-deadline&page=2"


def test_task_topic_is_typed_reused_and_preserved_on_edit(client, ui_data):
    from academics.models import Subject, Topic

    client.force_login(ui_data["owner"])
    payload = {
        "title": "Завдання з темою",
        "subject": ui_data["subject"].pk,
        "topic_name": "  Нова тема  ",
        "starts_on": "2026-11-01",
        "deadline": "2026-11-20T12:00",
        "work_type": "independent",
        "priority": "normal",
    }
    response = client.post(reverse("tasks:create"), payload)
    assert response.status_code == 302
    task = Task.objects.get(title=payload["title"])
    assert task.starts_on.isoformat() == "2026-11-01"
    assert task.topic.name == "Нова тема"
    assert task.topic.subject == ui_data["subject"]
    response = client.get(reverse("tasks:edit", args=[task.pk]))
    assert response.context["form"]["topic_name"].value() == "Нова тема"
    assert response.context["form"]["subject"].label == "Предмет"
    assert 'name="topic_name"' in response.content.decode()
    assert '<select name="topic"' not in response.content.decode()
    assert client.post(reverse("tasks:create"), {**payload, "title": "Друге завдання"}).status_code == 302
    assert Topic.objects.filter(subject=ui_data["subject"], name="Нова тема").count() == 1
    new_subject = Subject.objects.create(semester=ui_data["semester"], name="Інший предмет", teacher_name="Викладач")
    payload["subject"] = new_subject.pk
    assert client.post(reverse("tasks:edit", args=[task.pk]), payload).status_code == 302
    task.refresh_from_db()
    assert task.topic.subject == new_subject
    assert task.topic.name == "Нова тема"
    payload.update(topic_name="", starts_on="")
    assert client.post(reverse("tasks:edit", args=[task.pk]), payload).status_code == 302
    task.refresh_from_db()
    assert task.topic is None
    assert task.starts_on is None


@pytest.mark.parametrize("start", ["2026-11-21", "invalid-date"])
def test_task_start_date_validation_does_not_create_task_or_topic(client, ui_data, start):
    from academics.models import Topic

    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": "Некоректний початок",
            "subject": ui_data["subject"].pk,
            "topic_name": "Не зберігати",
            "starts_on": start,
            "deadline": "2026-11-20T12:00",
            "work_type": "independent",
            "priority": "normal",
        },
    )
    assert response.status_code == 200
    assert "starts_on" in response.context["form"].errors
    assert not Task.objects.filter(title="Некоректний початок").exists()
    assert not Topic.objects.filter(name="Не зберігати").exists()


def test_multiple_task_files_and_link_lists_create_and_edit(client, ui_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(ui_data["owner"])
    payload = {
        "title": "Кілька матеріалів",
        "subject": ui_data["subject"].pk,
        "deadline": "2027-01-20T12:00",
        "work_type": "independent",
        "priority": "normal",
        "attachment_url": ["https://example.com/lecture", "https://example.com/book"],
        "submission_urls": ["https://example.com/submit", "https://example.com/backup"],
        "attachment": [SimpleUploadedFile("one.txt", b"one"), SimpleUploadedFile("two.txt", b"two")],
    }
    response = client.post(reverse("tasks:create"), payload)
    assert response.status_code == 302
    task = Task.objects.get(title=payload["title"])
    assert task.attachments.exclude(file="").count() == 2
    assert set(task.attachments.exclude(url="").values_list("url", flat=True)) == set(payload["attachment_url"])
    assert set(task.submission_links.values_list("url", flat=True)) == set(payload["submission_urls"])
    response = client.get(reverse("tasks:edit", args=[task.pk]))
    assert response.context["form"]["attachment_url"].value() == payload["attachment_url"]
    assert response.context["form"]["submission_urls"].value() == payload["submission_urls"]
    assert "multiple" in response.content.decode()
    payload.update(
        attachment_url=["https://example.com/book", "https://example.com/new"],
        submission_urls=["https://example.com/backup"],
    )
    payload["attachment"] = [SimpleUploadedFile("three.txt", b"three")]
    response = client.post(reverse("tasks:edit", args=[task.pk]), payload)
    assert response.status_code == 302
    assert task.attachments.exclude(file="").count() == 3
    assert set(task.attachments.exclude(url="").values_list("url", flat=True)) == set(payload["attachment_url"])
    assert list(task.submission_links.values_list("url", flat=True)) == payload["submission_urls"]
    payload.pop("attachment")
    payload.update(attachment_url=[""], submission_urls=[""])
    assert client.post(reverse("tasks:edit", args=[task.pk]), payload).status_code == 302
    assert task.attachments.count() == 3
    assert not task.submission_links.exists()


@pytest.mark.parametrize("field", ["attachment_url", "submission_urls"])
@pytest.mark.parametrize(
    "links",
    [["https://example.com/good", "not a url"], ["https://example.com/repeated", "https://example.com/repeated"]],
)
def test_each_link_is_validated_and_invalid_values_are_preserved(client, ui_data, field, links):
    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": "Некоректні матеріали",
            "subject": ui_data["subject"].pk,
            "deadline": "2027-01-20T12:00",
            "work_type": "independent",
            "priority": "normal",
            field: links,
        },
    )
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert response.context["form"][field].value() == links
    assert not Task.objects.filter(title="Некоректні матеріали").exists()


def test_every_uploaded_file_is_validated_before_saving(client, ui_data, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": "Завеликий другий файл",
            "subject": ui_data["subject"].pk,
            "deadline": "2027-01-20T12:00",
            "work_type": "independent",
            "priority": "normal",
            "attachment": [
                SimpleUploadedFile("small.txt", b"small"),
                SimpleUploadedFile("large.txt", b"x" * (10 * 1024 * 1024 + 1)),
            ],
        },
    )
    assert response.status_code == 200
    assert "attachment" in response.context["form"].errors
    assert not Task.objects.filter(title="Завеликий другий файл").exists()
    assert not list(tmp_path.rglob("*.txt"))


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_task_priority_choices_are_saved_and_shown(client, ui_data, priority):
    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": f"Пріоритет {priority}",
            "subject": ui_data["subject"].pk,
            "deadline": "2027-01-20T12:00",
            "work_type": "independent",
            "priority": priority,
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title=f"Пріоритет {priority}")
    assert task.priority == priority
    detail = client.get(reverse("tasks:detail", args=[task.pk]))
    assert f"priority-{priority}" in detail.content.decode()
    edit = client.get(reverse("tasks:edit", args=[task.pk]))
    assert edit.context["form"]["priority"].value() == priority
    assert list(edit.context["form"].fields["priority"].choices) == [
        ("normal", "Звичайний"),
        ("high", "Високий"),
        ("low", "Низький"),
    ]


@pytest.mark.parametrize("priority", ["low", "normal", "high"])
def test_task_filters_support_every_priority_in_both_views(client, ui_data, priority):
    client.force_login(ui_data["owner"])
    selected = Task.objects.create(
        subject=ui_data["subject"], title=f"Filter {priority}", priority=priority, deadline=ui_data["task"].deadline
    )
    for mode in ("list", "table"):
        response = client.get(reverse("tasks:list"), {"priority": priority, "view": mode, "sort": "-deadline"})
        items = list(response.context["page"])
        assert selected in items
        assert all(task.priority == priority for task in items)
        assert 'name="sort" value="-deadline"' in response.content.decode()


@pytest.mark.parametrize("field", ["attachment_url", "submission_urls"])
def test_task_links_accept_uppercase_http_scheme(client, ui_data, field):
    client.force_login(ui_data["owner"])
    response = client.post(
        reverse("tasks:create"),
        {
            "title": f"Uppercase {field}",
            "subject": ui_data["subject"].pk,
            "deadline": "2027-01-20T12:00",
            "work_type": "independent",
            "priority": "normal",
            field: ["HTTPS://example.com/material"],
        },
    )
    assert response.status_code == 302
