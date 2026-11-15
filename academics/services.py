"""Curriculum mutations use the group's own permissions, including for deputies."""

from django.db import transaction

from students.models import GroupPermission, StudyGroup
from students.services import _require_permission

from .models import Semester, Subject, Topic


@transaction.atomic
def create_semester(user, group_id, **fields):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.MANAGE_ACADEMICS)
    semester = Semester(group=group, **fields)
    semester.full_clean()
    semester.save()
    return semester


@transaction.atomic
def activate_semester(user, semester_id):
    group_id = Semester.objects.values_list("group_id", flat=True).get(pk=semester_id)
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.MANAGE_ACADEMICS)
    semester = Semester.objects.get(pk=semester_id, group=group)
    Semester.objects.filter(group=group, is_active=True).update(is_active=False)
    semester.is_active = True
    semester.save(update_fields=["is_active"])
    return semester


@transaction.atomic
def create_subject(user, semester_id, **fields):
    semester = Semester.objects.select_related("group").get(pk=semester_id)
    _require_permission(user, semester.group, GroupPermission.MANAGE_ACADEMICS)
    subject = Subject(semester=semester, **fields)
    subject.full_clean()
    subject.save()
    return subject


@transaction.atomic
def create_topic(user, subject_id, *, name, position=0):
    subject = Subject.objects.select_related("semester__group").get(pk=subject_id)
    _require_permission(user, subject.group, GroupPermission.MANAGE_ACADEMICS)
    topic = Topic(subject=subject, name=name.strip(), position=position)
    topic.full_clean()
    topic.save()
    return topic


@transaction.atomic
def update_subject(user, subject_id, **fields):
    from django.core.exceptions import ValidationError

    subject = Subject.objects.select_for_update().select_related("semester__group").get(pk=subject_id)
    _require_permission(user, subject.group, GroupPermission.MANAGE_ACADEMICS)
    if fields.keys() - {
        "name",
        "semester",
        "description",
        "teacher_name",
        "teacher_email",
        "teacher_phone",
        "teacher_contact",
        "is_archived",
    }:
        raise ValidationError("Невідомі поля предмета.")
    if "semester" in fields and fields["semester"].group_id != subject.semester.group_id:
        raise ValidationError("Не можна переносити предмет до чужої групи.")
    for key, value in fields.items():
        setattr(subject, key, value)
    subject.full_clean()
    subject.save()
    return subject


@transaction.atomic
def update_semester(user, semester_id, **fields):
    from django.core.exceptions import ValidationError

    semester = Semester.objects.select_for_update().select_related("group").get(pk=semester_id)
    _require_permission(user, semester.group, GroupPermission.MANAGE_ACADEMICS)
    if fields.keys() - {"name", "academic_year_start", "starts_on", "ends_on"}:
        raise ValidationError("Невідомі поля семестру.")
    for key, value in fields.items():
        setattr(semester, key, value)
    semester.full_clean()
    semester.save()
    return semester


@transaction.atomic
def update_course(user, group_id, *, course):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.MANAGE_ACADEMICS)
    group.course = course
    group.full_clean()
    group.save(update_fields=["course"])
    return group
