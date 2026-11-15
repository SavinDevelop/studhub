"""Group operations with membership checks, role permissions and atomic changes."""

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    GroupInvitation,
    GroupMembership,
    GroupPermission,
    GroupRole,
    GroupRolePolicy,
    JoinRequest,
    StudentProfile,
    StudyGroup,
)


def _require_student(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    if not StudentProfile.objects.filter(user=user, completed_at__isnull=False).exists():
        raise PermissionDenied("Спочатку заповніть профіль.")


def _lock_user(user):
    return get_user_model().objects.select_for_update().get(pk=user.pk)


def has_group_permission(user, group, permission):
    if permission not in GroupPermission.values or not user.is_authenticated or not user.is_active:
        return False
    membership = GroupMembership.objects.filter(group=group, user=user).first()
    if membership is None:
        return False
    if group.owner_id == user.pk:
        return True
    policy = GroupRolePolicy.objects.filter(group=group, role=membership.role).first()
    return bool(policy and getattr(policy, permission))


def _require_permission(user, group, permission):
    _require_student(user)
    if not has_group_permission(user, group, permission):
        raise PermissionDenied("Ви не маєте права виконувати цю дію в групі.")


def _require_owner(user, group):
    _require_student(user)
    if group.owner_id != user.pk:
        raise PermissionDenied("Цю дію може виконувати лише власник групи.")


def get_user_group(user, group_id=None):
    _require_student(user)
    if group_id is not None:
        return get_group(user, group_id)
    membership = GroupMembership.objects.select_related("group").filter(user=user).first()
    return membership.group if membership else None


def get_group(user, group_id):
    _require_student(user)
    group = StudyGroup.objects.get(pk=group_id)
    if not GroupMembership.objects.filter(group=group, user=user).exists():
        raise PermissionDenied
    return group


@transaction.atomic
def create_group(user, *, name, description="", course=1):
    _require_student(user)
    _lock_user(user)
    group = StudyGroup(owner=user, name=name.strip(), description=description.strip(), course=course)
    group.full_clean()
    group.save()
    GroupMembership.objects.create(group=group, user=user)
    GroupRolePolicy.objects.create(group=group, role=GroupRole.STUDENT)
    GroupRolePolicy.objects.create(
        group=group,
        role=GroupRole.DEPUTY,
        can_invite=True,
        can_approve=True,
        can_manage_tasks=True,
        can_manage_academics=True,
    )
    return group


@transaction.atomic
def update_group(user, group_id, *, name):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.EDIT_GROUP)
    group.name = name.strip()
    group.full_clean()
    group.save(update_fields=["name"])
    return group


@transaction.atomic
def set_member_role(user, group_id, *, member_id, role):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_owner(user, group)
    member = GroupMembership.objects.get(pk=member_id, group=group)
    if member.user_id == group.owner_id:
        raise ValidationError("Не можна змінити роль власника.")
    if role not in GroupRole.values:
        raise ValidationError("Невідома роль.")
    member.role = role
    member.full_clean()
    member.save(update_fields=["role"])
    return member


@transaction.atomic
def set_role_permissions(user, group_id, *, role, **permissions):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_owner(user, group)
    if role not in GroupRole.values:
        raise ValidationError("Невідома роль.")
    if permissions.keys() - set(GroupPermission.values) or any(
        type(value) is not bool for value in permissions.values()
    ):
        raise ValidationError("Передайте лише відомі права з булевими значеннями.")
    policy = GroupRolePolicy.objects.get(group=group, role=role)
    for field, value in permissions.items():
        setattr(policy, field, value)
    policy.full_clean()
    policy.save()
    return policy


@transaction.atomic
def create_invitation(user, group_id, *, expires_at=None, email="", max_uses=20):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.INVITE)
    invitation = GroupInvitation(group=group, created_by=user, email=email.strip().lower(), max_uses=max_uses)
    if expires_at is not None:
        invitation.expires_at = expires_at
    invitation.full_clean()
    if timezone.is_naive(invitation.expires_at) or invitation.expires_at <= timezone.now():
        raise ValidationError("Строк запрошення має бути в майбутньому та містити часовий пояс.")
    invitation.save()
    return invitation


@transaction.atomic
def revoke_invitation(user, invitation_id):
    group_id = GroupInvitation.objects.values_list("group_id", flat=True).get(pk=invitation_id)
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.INVITE)
    invitation = GroupInvitation.objects.get(pk=invitation_id, group=group)
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    return invitation


def get_invitation(token):
    invitation = GroupInvitation.objects.select_related("group").get(token=token)
    if not invitation.is_active:
        raise ValidationError("Запрошення відкликане, вичерпане або строк його дії закінчився.")
    return invitation


@transaction.atomic
def request_to_join(user, token):
    _require_student(user)
    invitation = get_invitation(token)
    StudyGroup.objects.select_for_update().get(pk=invitation.group_id)
    _lock_user(user)
    # Re-read after acquiring the group lock: a concurrent revocation wins.
    invitation = get_invitation(token)
    if GroupMembership.objects.filter(user=user, group=invitation.group).exists():
        raise ValidationError("Ви вже належите до цієї групи.")
    if (
        invitation.email
        and not EmailAddress.objects.filter(user=user, email__iexact=invitation.email, verified=True).exists()
    ):
        raise PermissionDenied("Підтвердіть email, на який надіслано запрошення.")
    join_request, created = JoinRequest.objects.get_or_create(
        group=invitation.group,
        user=user,
        defaults={"invitation": invitation},
    )
    resubmitted = not created and join_request.status != JoinRequest.Status.PENDING
    if resubmitted:
        join_request.status = JoinRequest.Status.PENDING
        join_request.invitation = invitation
        join_request.reviewed_at = None
        join_request.reviewed_by = None
        join_request.save()
    if created or resubmitted:
        invitation.use_count += 1
        invitation.save(update_fields=["use_count"])
    return join_request


@transaction.atomic
def review_join_request(user, request_id, *, approve):
    if type(approve) is not bool:
        raise ValidationError("Передайте рішення про схвалення.")
    group_id = JoinRequest.objects.values_list("group_id", flat=True).get(pk=request_id)
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.APPROVE)
    join_request = JoinRequest.objects.select_related("user").get(pk=request_id, group=group)
    if join_request.user_id == user.pk:
        raise PermissionDenied("Не можна схвалити власну заявку.")
    _lock_user(join_request.user)
    join_request = JoinRequest.objects.select_for_update().select_related("user").get(pk=request_id, group=group)
    if join_request.status != JoinRequest.Status.PENDING:
        raise ValidationError("Заявка вже розглянута.")
    if approve:
        _require_student(join_request.user)
        if GroupMembership.objects.filter(user=join_request.user, group=group).exists():
            raise ValidationError("Студент уже належить до групи.")
        GroupMembership.objects.create(group=group, user=join_request.user)
    join_request.status = JoinRequest.Status.APPROVED if approve else JoinRequest.Status.REJECTED
    join_request.reviewed_at = timezone.now()
    join_request.reviewed_by = user
    join_request.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    return join_request


@transaction.atomic
def remove_member(user, group_id, *, member_id):
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    _require_permission(user, group, GroupPermission.REMOVE_MEMBERS)
    member = GroupMembership.objects.get(pk=member_id, group=group)
    if member.user_id == group.owner_id:
        raise ValidationError("Не можна видалити власника групи.")
    if group.owner_id != user.pk and (member.role == GroupRole.DEPUTY or member.user_id == user.pk):
        raise PermissionDenied("Видаляти заступників може лише власник.")
    _lock_user(member.user)
    member.delete()


@transaction.atomic
def leave_group(user, group_id):
    _require_student(user)
    group = StudyGroup.objects.select_for_update().get(pk=group_id)
    if group.owner_id == user.pk:
        raise ValidationError("Власник не може залишити свою групу.")
    _lock_user(user)
    GroupMembership.objects.get(group=group, user=user).delete()
