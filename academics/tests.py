from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from students.models import GroupMembership, GroupPermission, GroupRole, StudentProfile
from students.services import create_group, set_role_permissions

from .models import Semester, Subject
from .services import activate_semester, create_semester, create_subject, create_topic

pytestmark = pytest.mark.django_db


@pytest.fixture
def curriculum(django_user_model):
    owner = django_user_model.objects.create_user(username="owner")
    StudentProfile.objects.create(user=owner, first_name="Марія", last_name="Коваль", completed_at=timezone.now())
    group = create_group(owner, name="ПМНБ-26-1", course=2)
    semester = create_semester(
        owner,
        group.pk,
        name="Осінь 2026",
        academic_year_start=2026,
        starts_on=date(2026, 9, 1),
        ends_on=date(2026, 12, 31),
        is_active=True,
    )
    return owner, group, semester


def test_active_semester_is_per_group_and_can_be_historical(curriculum):
    owner, group, first = curriculum
    spring = create_semester(
        owner,
        group.pk,
        name="Весна 2026",
        academic_year_start=2025,
        starts_on=date(2026, 2, 1),
        ends_on=date(2026, 5, 31),
    )
    activate_semester(owner, spring.pk)
    first.refresh_from_db()
    assert not first.is_active
    assert group.semesters.get(is_active=True) == spring
    assert spring.academic_year == "2025 / 2026"
    assert first.subjects.count() == 0


def test_semester_constraints_at_database_level(curriculum):
    _, group, _ = curriculum
    with pytest.raises(IntegrityError), transaction.atomic():
        Semester.objects.create(
            group=group,
            name="Другий активний",
            academic_year_start=2026,
            starts_on=date(2027, 2, 1),
            ends_on=date(2027, 5, 31),
            is_active=True,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Semester.objects.create(
            group=group,
            name="Некоректні дати",
            academic_year_start=2026,
            starts_on=date(2027, 5, 31),
            ends_on=date(2027, 2, 1),
        )


def test_subject_teacher_contacts_and_topic_are_scoped(curriculum):
    owner, group, semester = curriculum
    subject = create_subject(
        owner,
        semester.pk,
        name="Міжнародне право",
        teacher_name="Чернецька О.В.",
        teacher_email="teacher@example.com",
        teacher_phone="+380123456789",
        teacher_contact="@teacher",
        description="Право та міжнародні відносини",
    )
    topic = create_topic(owner, subject.pk, name="Права людини")
    assert subject.group == group
    assert topic.subject.semester == semester
    with pytest.raises(ValidationError):
        create_subject(owner, semester.pk, name=subject.name, teacher_name="Інший викладач")
    with pytest.raises(ValidationError):
        create_subject(owner, semester.pk, name="Без викладача", teacher_name="")


def test_academic_permissions_do_not_leak_across_groups(curriculum, django_user_model):
    owner, group, semester = curriculum
    deputy = django_user_model.objects.create_user(username="deputy")
    StudentProfile.objects.create(user=deputy, first_name="Олег", last_name="Коваль", completed_at=timezone.now())
    GroupMembership.objects.create(user=deputy, group=group, role=GroupRole.DEPUTY)
    assert create_subject(deputy, semester.pk, name="Фізика", teacher_name="Викладач")
    other = create_group(owner, name="Інша група")
    other_semester = create_semester(
        owner, other.pk, name="Осінь", academic_year_start=2026, starts_on=date(2026, 9, 1), ends_on=date(2026, 12, 31)
    )
    with pytest.raises(PermissionDenied):
        create_subject(deputy, other_semester.pk, name="Хімія", teacher_name="Викладач")
    set_role_permissions(owner, group.pk, role=GroupRole.DEPUTY, **{GroupPermission.MANAGE_ACADEMICS: False})
    with pytest.raises(PermissionDenied):
        activate_semester(deputy, semester.pk)
    assert Subject.objects.count() == 1


def test_semester_can_be_created_without_year_or_end_date(client, curriculum):
    from django.urls import reverse

    owner, group, _ = curriculum
    client.force_login(owner)
    response = client.post(reverse("academics:semester_create"), {"name": "Новий семестр", "starts_on": "2027-02-01"})
    assert response.status_code == 302
    assert response.url == reverse("academics:curriculum", args=[group.pk])
    semester = group.semesters.get(name="Новий семестр")
    assert semester.ends_on is None
    assert semester.academic_year_start is None
    assert semester.starts_on == date(2027, 2, 1)


def test_semester_end_date_can_be_cleared_but_cannot_precede_start(client, curriculum):
    from django.urls import reverse

    owner, _, semester = curriculum
    client.force_login(owner)
    url = reverse("academics:semester_edit", args=[semester.pk])
    response = client.post(url, {"name": semester.name, "starts_on": "2026-09-01", "ends_on": "2026-08-01"})
    assert response.status_code == 200
    assert response.context["form"].errors
    semester.refresh_from_db()
    assert semester.ends_on == date(2026, 12, 31)
    response = client.post(url, {"name": semester.name, "starts_on": "2026-09-01", "ends_on": ""})
    assert response.status_code == 302
    semester.refresh_from_db()
    assert semester.ends_on is None


def test_curriculum_contains_semester_management_and_legacy_page_redirects(client, curriculum):
    from django.urls import reverse

    owner, group, semester = curriculum
    client.force_login(owner)
    url = reverse("academics:curriculum", args=[group.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert semester in response.context["semesters"]
    assert 'id="semesters"' in response.content.decode()
    assert all(item["key"] != "semesters" for item in response.context["workspace"]["group_nav"])
    response = client.get(reverse("academics:semesters"))
    assert response.status_code == 302
    assert response.url == url
    response = client.post(reverse("academics:activate", args=[semester.pk]))
    assert response.status_code == 302
    assert response.url == url
