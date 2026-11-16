from urllib.parse import urlencode

import pytest
from allauth.socialaccount.models import SocialAccount
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

from .models import GroupMembership, GroupRole, JoinRequest, StudentProfile
from .services import create_invitation, request_to_join, set_member_role

pytestmark = pytest.mark.django_db


def test_anonymous_user_redirected_to_login(client):
    response = client.get(reverse("students:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))


def test_first_login_requires_explicit_profile_confirmation(client, student_factory):
    user = student_factory(complete=False)
    client.force_login(user)
    response = client.get(reverse("students:dashboard"), follow=True)
    assert response.status_code == 200
    assert response.resolver_match.view_name == "students:profile"
    assert not StudentProfile.objects.get(user=user).completed_at
    response = client.post(reverse("students:profile"), {"first_name": "Олена", "last_name": "Коваль"})
    assertRedirects(response, reverse("students:dashboard"))
    assert StudentProfile.objects.get(user=user).completed_at is not None


def test_google_profile_prefill_visible_and_editable(client, student_factory):
    user = student_factory(complete=False)
    SocialAccount.objects.create(
        user=user,
        provider="google",
        uid="123",
        extra_data={
            "given_name": "Олена",
            "family_name": "Коваль",
            "picture": "https://example.com/photo.jpg",
        },
    )
    client.force_login(user)
    response = client.get(reverse("students:profile"))
    assertContains(response, 'value="Олена"')
    assertContains(response, 'value="Коваль"')
    assertContains(response, "https://example.com/photo.jpg")
    client.post(reverse("students:profile"), {"first_name": "Ірина", "last_name": "Коваль"})
    assert StudentProfile.objects.get(user=user).first_name == "Ірина"


def test_profile_form_errors_do_not_complete_profile(client, student_factory):
    user = student_factory(complete=False)
    client.force_login(user)
    response = client.post(reverse("students:profile"), {"first_name": " ", "last_name": "Коваль"})
    assert response.status_code == 200
    assert response.context["form"].errors
    assert StudentProfile.objects.get(user=user).completed_at is None


@pytest.mark.parametrize("destination", ["https://attacker.example/", "//attacker.example/", "/profile/"])
def test_profile_confirmation_cannot_redirect_externally_or_loop(client, student_factory, destination):
    client.force_login(student_factory(complete=False))
    response = client.post(
        reverse("students:profile"), {"first_name": "Олена", "last_name": "Коваль", "next": destination}
    )
    assertRedirects(response, reverse("students:dashboard"))


def test_invitation_is_preserved_through_profile_confirmation(client, student_factory, owner, group):
    invitation = create_invitation(owner, group.pk)
    url = reverse("students:invitation", args=[invitation.token])
    client.force_login(student_factory(complete=False))
    response = client.get(url, follow=True)
    assert response.context["next"] == url
    response = client.post(reverse("students:profile"), {"first_name": "Олена", "last_name": "Коваль", "next": url})
    assertRedirects(response, url)
    assert not JoinRequest.objects.exists()
    response = client.post(url)
    assert response.status_code == 302
    assert JoinRequest.objects.get().status == JoinRequest.Status.PENDING


def test_invitation_get_never_submits_request(client, student_factory, owner, group):
    user = student_factory()
    client.force_login(user)
    invitation = create_invitation(owner, group.pk)
    assert client.get(reverse("students:invitation", args=[invitation.token])).status_code == 200
    assert not JoinRequest.objects.exists()
    assert not GroupMembership.objects.filter(user=user).exists()


def test_invitation_survives_signup_then_profile_confirmation(client, owner, group, settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    invitation = create_invitation(owner, group.pk)
    url = reverse("students:invitation", args=[invitation.token])
    response = client.get(url, follow=True)
    assert response.resolver_match.view_name == "account_login"
    signup_url = reverse("account_signup") + "?" + urlencode({"next": url}, safe="/")
    assertContains(response, signup_url)
    response = client.get(signup_url)
    assert response.context["redirect_field_value"] == url
    response = client.post(
        reverse("account_signup"),
        {
            "email": "new@example.com",
            "password1": "Study!9-secure-2026",
            "password2": "Study!9-secure-2026",
            "next": url,
        },
        follow=True,
    )
    assert response.resolver_match.view_name == "students:profile"
    assert response.context["next"] == url
    response = client.post(
        reverse("students:profile"),
        {
            "first_name": "Олена",
            "last_name": "Коваль",
            "next": url,
        },
        follow=True,
    )
    assert response.resolver_match.view_name == "students:invitation"
    assert not JoinRequest.objects.exists()
    client.post(url)
    assert JoinRequest.objects.get(user__email="new@example.com").status == JoinRequest.Status.PENDING


def test_owner_can_save_role_policy_via_form(client, owner, group):
    client.force_login(owner)
    response = client.post(
        reverse("students:role_permissions", args=[group.pk, "student"]),
        {
            "can_invite": "on",
            "can_approve": "on",
        },
    )
    assertRedirects(response, reverse("students:group", args=[group.pk]))
    policy = group.role_policies.get(role=GroupRole.STUDENT)
    assert policy.can_invite is True
    assert policy.can_approve is True
    assert policy.can_remove_members is False


def test_group_create_page_and_member_view(client, student_factory):
    user = student_factory()
    client.force_login(user)
    response = client.post(reverse("students:create_group"), {"name": "КН-21"}, follow=True)
    assert response.status_code == 200
    assert response.resolver_match.view_name == "students:group"
    assertContains(response, "КН-21")
    assertContains(response, reverse("students:group_permissions", args=[response.context["group"].pk]))
    assertContains(response, "Дозволи")


def test_group_information_and_actions_denied_to_outsiders(client, student_factory, group):
    client.force_login(student_factory())
    assert client.get(reverse("students:group", args=[group.pk])).status_code == 403
    assert client.post(reverse("students:create_invitation", args=[group.pk])).status_code == 403
    assert (
        client.post(
            reverse("students:role_permissions", args=[group.pk, GroupRole.DEPUTY]), {"can_approve": True}
        ).status_code
        == 403
    )


def test_review_request_cannot_be_forged_for_another_group(client, owner, group, student_factory):
    from .services import create_group

    other_owner = student_factory()
    other = create_group(other_owner, name="Інша")
    application = request_to_join(student_factory(), create_invitation(other_owner, other.pk).token)
    client.force_login(owner)
    response = client.post(reverse("students:review_request", args=[group.pk, application.pk, "approve"]))
    assert response.status_code == 404
    application.refresh_from_db()
    assert application.status == JoinRequest.Status.PENDING


def test_deputy_cannot_promote_self_or_edit_policy_over_http(client, owner, group, member_factory):
    deputy = member_factory()
    member_id = deputy.group_memberships.get(group=group).pk
    set_member_role(owner, group.pk, member_id=member_id, role=GroupRole.DEPUTY)
    client.force_login(deputy)
    assert (
        client.post(reverse("students:member_role", args=[group.pk, member_id]), {"role": "deputy"}).status_code == 403
    )
    assert (
        client.post(
            reverse("students:role_permissions", args=[group.pk, "deputy"]), {"can_remove_members": True}
        ).status_code
        == 403
    )


def test_owner_can_review_request_from_group_page(client, owner, group, student_factory):
    applicant = student_factory()
    application = request_to_join(applicant, create_invitation(owner, group.pk).token)
    client.force_login(owner)
    response = client.get(reverse("students:group", args=[group.pk]))
    assertContains(response, str(applicant.student_profile))
    response = client.post(reverse("students:review_request", args=[group.pk, application.pk, "approve"]))
    assertRedirects(response, reverse("students:group", args=[group.pk]))
    assert applicant.group_memberships.get(group=group).group == group


@pytest.mark.parametrize(
    "route",
    [
        "create_group",
        "create_invitation",
        "member_role",
        "role_permissions",
        "review_request",
        "remove_member",
        "leave_group",
        "revoke_invitation",
        "update_group",
    ],
)
def test_mutations_require_post(client, owner, group, route):
    client.force_login(owner)
    kwargs = {} if route == "create_group" else {"group_id": group.pk}
    if route in {"member_role", "remove_member"}:
        kwargs["member_id"] = owner.group_memberships.get(group=group).pk
    if route == "role_permissions":
        kwargs["role"] = "deputy"
    if route == "review_request":
        kwargs.update(request_id=1, decision="approve")
    if route == "revoke_invitation":
        kwargs["invitation_id"] = 1
    assert client.get(reverse(f"students:{route}", kwargs=kwargs)).status_code == 405


@pytest.mark.parametrize("route", ["profile", "create_group", "create_invitation", "role_permissions", "invitation"])
def test_profile_and_group_forms_require_csrf(owner, group, route):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    kwargs = {}
    if route in {"create_invitation", "role_permissions"}:
        kwargs["group_id"] = group.pk
    if route == "role_permissions":
        kwargs["role"] = "deputy"
    if route == "invitation":
        kwargs["token"] = create_invitation(owner, group.pk).token
    assert client.post(reverse(f"students:{route}", kwargs=kwargs), {}).status_code == 403


def test_profile_email_is_disabled_and_change_uses_dialog(client, student_factory):
    user = student_factory()
    client.force_login(user)
    response = client.get(reverse("students:account_settings"))
    assertContains(response, f'value="{user.email}" disabled')
    assertContains(response, 'data-dialog="change-email-dialog"')
    assertContains(response, 'id="change-email-dialog"')
    assertContains(response, reverse("students:change_email"))
    assertRedirects(client.get(reverse("students:change_email")), reverse("students:account_settings"))
    assertRedirects(client.get(reverse("account_email")), reverse("students:account_settings"))


@pytest.mark.parametrize("email", ["invalid", "student0@example.com"])
def test_invalid_email_change_reopens_modal_without_changing_profile(client, student_factory, email):
    user = student_factory()
    client.force_login(user)
    response = client.post(reverse("students:change_email"), {"email": email, "action_add": ""})
    assert response.status_code == 200
    assert response.context["email_form"].errors
    assert response.context["email_dialog_open"]
    assertContains(response, "data-auto-open")
    user.refresh_from_db()
    assert user.email == "student0@example.com"
    assert user.student_profile.first_name == "Олена"


def test_email_changes_only_after_new_address_is_confirmed(client, student_factory, settings, mailoutbox):
    from allauth.account.models import EmailAddress, EmailConfirmationHMAC

    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    user = student_factory()
    old_email = user.email
    EmailAddress.objects.create(user=user, email=old_email, primary=True, verified=True)
    client.force_login(user)
    response = client.post(reverse("students:change_email"), {"email": "updated-profile@example.com", "action_add": ""})
    assertRedirects(response, reverse("students:account_settings"))
    user.refresh_from_db()
    assert user.email == old_email
    pending = EmailAddress.objects.get(user=user, email="updated-profile@example.com")
    assert not pending.verified
    assert not pending.primary
    assert any("updated-profile@example.com" in message.to for message in mailoutbox)
    response = client.get(reverse("students:account_settings"))
    assert response.context["pending_email"] == pending
    key = EmailConfirmationHMAC(pending).key
    response = client.post(reverse("account_confirm_email", args=[key]))
    assert response.status_code == 302
    user.refresh_from_db()
    pending.refresh_from_db()
    assert user.email == "updated-profile@example.com"
    assert pending.verified
    assert pending.primary


def test_email_change_requires_login_and_csrf(client, student_factory):
    url = reverse("students:change_email")
    assert client.post(url, {"email": "new@example.com", "action_add": ""}).status_code == 302
    protected = Client(enforce_csrf_checks=True)
    protected.force_login(student_factory())
    assert protected.post(url, {"email": "new@example.com", "action_add": ""}).status_code == 403


@pytest.mark.parametrize("route", ["account_email", "students:change_email"])
def test_unverified_email_cannot_be_made_primary_through_legacy_action(client, student_factory, route):
    from allauth.account.models import EmailAddress

    user = student_factory()
    old = user.email
    EmailAddress.objects.create(user=user, email=old, primary=True, verified=False)
    EmailAddress.objects.create(user=user, email="pending@example.com", verified=False)
    client.force_login(user)
    response = client.post(reverse(route), {"email": "pending@example.com", "action_primary": ""})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.email == old
