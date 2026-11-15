from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import GroupInvitation, GroupMembership, GroupPermission, GroupRole, JoinRequest, StudyGroup
from .services import (
    create_group,
    create_invitation,
    get_group,
    has_group_permission,
    leave_group,
    remove_member,
    request_to_join,
    review_join_request,
    revoke_invitation,
    set_member_role,
    set_role_permissions,
    update_group,
)

pytestmark = pytest.mark.django_db


def test_group_creation_sets_owner_membership_and_default_policies(owner, group):
    assert group.owner == owner
    assert owner.group_memberships.get(group=group).group == group
    assert group.role_policies.count() == 2
    assert not group.role_policies.get(role=GroupRole.STUDENT).can_approve
    assert group.role_policies.get(role=GroupRole.DEPUTY).can_approve
    assert all(has_group_permission(owner, group, action) for action in GroupPermission)


@pytest.mark.parametrize("name", ["", "  ", "x" * 151])
def test_invalid_group_name_rolls_back(owner, name):
    with pytest.raises(ValidationError):
        create_group(owner, name=name)
    assert not StudyGroup.objects.exists()
    assert not GroupMembership.objects.exists()


def test_can_create_second_group(owner, group):
    other = create_group(owner, name="Інша")
    assert set(owner.group_memberships.values_list("group_id", flat=True)) == {group.pk, other.pk}


def test_incomplete_profile_cannot_create_group(student_factory):
    user = student_factory(complete=False)
    with pytest.raises(PermissionDenied):
        create_group(user, name="КН-21")


def test_invitation_only_creates_pending_request(owner, group, student_factory):
    user = student_factory()
    invitation = create_invitation(owner, group.pk)
    application = request_to_join(user, invitation.token)
    assert application.status == JoinRequest.Status.PENDING
    assert not GroupMembership.objects.filter(user=user).exists()
    assert request_to_join(user, invitation.token).pk == application.pk
    assert JoinRequest.objects.count() == 1
    review_join_request(owner, application.pk, approve=True)
    assert user.group_memberships.get(group=group).group == group
    application.refresh_from_db()
    assert application.reviewed_by == owner
    assert application.reviewed_at is not None
    with pytest.raises(ValidationError):
        review_join_request(owner, application.pk, approve=True)


@pytest.mark.parametrize("expired", [False, True])
def test_revoked_or_expired_invitation_rejected(owner, group, student_factory, expired):
    invitation = create_invitation(owner, group.pk)
    if expired:
        GroupInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    else:
        revoke_invitation(owner, invitation.pk)
    with pytest.raises(ValidationError):
        request_to_join(student_factory(), invitation.token)
    assert not JoinRequest.objects.exists()


def test_invitation_must_expire_in_future(owner, group):
    with pytest.raises(ValidationError):
        create_invitation(owner, group.pk, expires_at=timezone.now() - timedelta(days=1))


def test_multiple_deputies_can_approve(owner, group, member_factory, student_factory):
    deputies = [member_factory(), member_factory()]
    for deputy in deputies:
        set_member_role(owner, group.pk, member_id=deputy.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
        invitation = create_invitation(deputy, group.pk)
        applicant = student_factory()
        application = request_to_join(applicant, invitation.token)
        review_join_request(deputy, application.pk, approve=True)
        assert applicant.group_memberships.get(group=group).group_id == group.pk
    assert group.memberships.filter(role=GroupRole.DEPUTY).count() == 2


def test_student_denied_by_default_then_allowed_by_policy(owner, group, member_factory, student_factory):
    member = member_factory()
    invitation = create_invitation(owner, group.pk)
    application = request_to_join(student_factory(), invitation.token)
    with pytest.raises(PermissionDenied):
        review_join_request(member, application.pk, approve=True)
    with pytest.raises(PermissionDenied):
        create_invitation(member, group.pk)
    set_role_permissions(owner, group.pk, role=GroupRole.STUDENT, can_approve=True, can_invite=True)
    review_join_request(member, application.pk, approve=True)
    assert create_invitation(member, group.pk).created_by == member


def test_revoking_deputy_permission_takes_effect_immediately(owner, group, member_factory, student_factory):
    deputy = member_factory()
    set_member_role(owner, group.pk, member_id=deputy.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
    application = request_to_join(student_factory(), create_invitation(owner, group.pk).token)
    set_role_permissions(owner, group.pk, role=GroupRole.DEPUTY, can_approve=False)
    with pytest.raises(PermissionDenied):
        review_join_request(deputy, application.pk, approve=True)
    application.refresh_from_db()
    assert application.status == JoinRequest.Status.PENDING


def test_deputy_cannot_change_roles_or_permissions(owner, group, member_factory):
    deputy, member = member_factory(), member_factory()
    set_member_role(owner, group.pk, member_id=deputy.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
    with pytest.raises(PermissionDenied):
        set_member_role(deputy, group.pk, member_id=member.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
    with pytest.raises(PermissionDenied):
        set_role_permissions(deputy, group.pk, role=GroupRole.DEPUTY, can_remove_members=True)


def test_outsider_cannot_access_group_or_use_its_permissions(owner, group, student_factory):
    outsider = student_factory()
    assert not has_group_permission(outsider, group, GroupPermission.APPROVE)
    assert not has_group_permission(AnonymousUser(), group, GroupPermission.APPROVE)
    with pytest.raises(PermissionDenied):
        get_group(outsider, group.pk)
    with pytest.raises(PermissionDenied):
        create_invitation(outsider, group.pk)


def test_permissions_do_not_leak_between_groups(owner, group, student_factory):
    other_owner = student_factory()
    other = create_group(other_owner, name="Інша")
    application = request_to_join(student_factory(), create_invitation(other_owner, other.pk).token)
    with pytest.raises(PermissionDenied):
        review_join_request(owner, application.pk, approve=True)


def test_rejected_request_can_be_resubmitted(owner, group, student_factory):
    user = student_factory()
    invitation = create_invitation(owner, group.pk)
    application = request_to_join(user, invitation.token)
    review_join_request(owner, application.pk, approve=False)
    assert not GroupMembership.objects.filter(user=user).exists()
    resubmitted = request_to_join(user, invitation.token)
    assert resubmitted.pk == application.pk
    assert resubmitted.status == JoinRequest.Status.PENDING
    assert resubmitted.reviewed_by is None


def test_joining_group_keeps_other_pending_requests(owner, group, student_factory):
    other_owner = student_factory()
    other = create_group(other_owner, name="Інша")
    applicant = student_factory()
    first = request_to_join(applicant, create_invitation(owner, group.pk).token)
    second = request_to_join(applicant, create_invitation(other_owner, other.pk).token)
    review_join_request(owner, first.pk, approve=True)
    second.refresh_from_db()
    assert second.status == JoinRequest.Status.PENDING
    review_join_request(other_owner, second.pk, approve=True)
    assert GroupMembership.objects.filter(user=applicant).count() == 2
    with pytest.raises(ValidationError):
        request_to_join(applicant, create_invitation(other_owner, other.pk).token)


def test_owner_role_and_membership_are_protected(owner, group):
    with pytest.raises(ValidationError):
        set_member_role(owner, group.pk, member_id=owner.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
    with pytest.raises(ValidationError):
        remove_member(owner, group.pk, member_id=owner.group_memberships.get(group=group).pk)
    with pytest.raises(ValidationError):
        leave_group(owner, group.pk)


def test_deputy_can_remove_students_only_when_allowed(owner, group, member_factory):
    deputy, member, other_deputy = member_factory(), member_factory(), member_factory()
    for user in (deputy, other_deputy):
        set_member_role(owner, group.pk, member_id=user.group_memberships.get(group=group).pk, role=GroupRole.DEPUTY)
    with pytest.raises(PermissionDenied):
        remove_member(deputy, group.pk, member_id=member.group_memberships.get(group=group).pk)
    set_role_permissions(owner, group.pk, role=GroupRole.DEPUTY, can_remove_members=True)
    with pytest.raises(PermissionDenied):
        remove_member(deputy, group.pk, member_id=other_deputy.group_memberships.get(group=group).pk)
    remove_member(deputy, group.pk, member_id=member.group_memberships.get(group=group).pk)
    assert not GroupMembership.objects.filter(user=member).exists()


def test_member_can_leave_and_reapply(owner, group, member_factory):
    member = member_factory()
    leave_group(member, group.pk)
    application = request_to_join(member, create_invitation(owner, group.pk).token)
    assert application.status == JoinRequest.Status.PENDING


def test_group_rename_requires_permission(owner, group, member_factory):
    member = member_factory()
    with pytest.raises(PermissionDenied):
        update_group(member, group.pk, name="Нова")
    set_role_permissions(owner, group.pk, role=GroupRole.STUDENT, can_edit_group=True)
    assert update_group(member, group.pk, name=" Нова ").name == "Нова"


@pytest.mark.parametrize("permissions", [{"unknown": True}, {"can_invite": "false"}])
def test_invalid_permission_settings_rejected(owner, group, permissions):
    with pytest.raises(ValidationError):
        set_role_permissions(owner, group.pk, role=GroupRole.STUDENT, **permissions)


def test_membership_unique_only_within_group(owner, group):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        GroupMembership.objects.create(user=owner, group=group)


def test_invitation_limits_and_email_restriction(owner, group, student_factory):
    from allauth.account.models import EmailAddress

    invited = student_factory()
    invitation = create_invitation(owner, group.pk, email=invited.email, max_uses=1)
    with pytest.raises(PermissionDenied):
        request_to_join(student_factory(), invitation.token)
    with pytest.raises(PermissionDenied):
        request_to_join(invited, invitation.token)
    EmailAddress.objects.create(user=invited, email=invited.email, verified=True, primary=True)
    application = request_to_join(invited, invitation.token)
    invitation.refresh_from_db()
    assert invitation.use_count == 1
    assert not invitation.is_active
    with pytest.raises(ValidationError):
        request_to_join(student_factory(), invitation.token)
    # A reservation created before exhaustion can still be approved.
    review_join_request(owner, application.pk, approve=True)
    assert GroupMembership.objects.filter(user=invited, group=group).exists()


def test_roles_are_independent_in_multiple_groups(owner, group, student_factory):
    member = student_factory()
    GroupMembership.objects.create(user=member, group=group, role=GroupRole.DEPUTY)
    other = create_group(member, name="Власна група")
    assert has_group_permission(member, group, GroupPermission.MANAGE_TASKS)
    assert not has_group_permission(member, group, GroupPermission.VIEW_ANALYTICS)
    assert has_group_permission(member, other, GroupPermission.VIEW_ANALYTICS)
    set_role_permissions(owner, group.pk, role=GroupRole.DEPUTY, can_manage_tasks=False)
    assert not has_group_permission(member, group, GroupPermission.MANAGE_TASKS)
    assert has_group_permission(member, other, GroupPermission.MANAGE_TASKS)
