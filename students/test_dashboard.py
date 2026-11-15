import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

from .models import StudentProfile, StudyGroup
from .services import create_invitation, request_to_join

pytestmark = pytest.mark.django_db


def test_dashboard_links_to_group_creation_and_account_settings(client, student_factory):
    user = student_factory()
    client.force_login(user)
    response = client.get(reverse("students:dashboard"))
    assertContains(response, reverse("students:new_group"))
    assertContains(response, reverse("students:account_settings"))
    assertContains(response, user.first_name)


def test_new_group_page_does_not_create_group(client, student_factory):
    client.force_login(student_factory())
    response = client.get(reverse("students:new_group"))
    assertContains(response, reverse("students:create_group"))
    assert not StudyGroup.objects.exists()


def test_group_form_preserves_errors_on_dedicated_page(client, student_factory):
    client.force_login(student_factory())
    response = client.post(reverse("students:create_group"), {"name": " "})
    assert response.status_code == 400
    assert response.templates[0].name == "students/new_group.html"
    assert response.context["form"].errors
    assert not StudyGroup.objects.exists()


def test_member_dashboard_shows_group_and_allows_creation(client, owner, group):
    client.force_login(owner)
    response = client.get(reverse("students:dashboard"))
    assertContains(response, group.name)
    assertContains(response, "Староста")
    assert response.context["member_count"] == 1
    assertContains(response, reverse("students:new_group"))
    assert client.get(reverse("students:new_group")).status_code == 200


def test_dashboard_reviews_only_visible_to_authorized_members(client, owner, group, member_factory, student_factory):
    member = member_factory()
    request_to_join(student_factory(), create_invitation(owner, group.pk).token)
    client.force_login(owner)
    assert client.get(reverse("students:dashboard")).context["pending_reviews"] == 1
    client.force_login(member)
    assert client.get(reverse("students:dashboard")).context["pending_reviews"] == 0


def test_dashboard_only_shows_own_applications(client, owner, group, student_factory):
    applicant, other = student_factory(), student_factory()
    invitation = create_invitation(owner, group.pk)
    own = request_to_join(applicant, invitation.token)
    request_to_join(other, invitation.token)
    client.force_login(applicant)
    response = client.get(reverse("students:dashboard"))
    assert list(response.context["join_requests"]) == [own]


@pytest.mark.parametrize("route", ["new_group", "account_settings"])
def test_new_pages_require_login_and_completed_profile(client, student_factory, route):
    url = reverse(f"students:{route}")
    response = client.get(url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))
    client.force_login(student_factory(complete=False))
    response = client.get(url, follow=True)
    assert response.resolver_match.view_name == "students:profile"


def test_settings_update_only_current_profile(client, student_factory):
    user, other = student_factory(), student_factory()
    client.force_login(user)
    response = client.post(
        reverse("students:account_settings"),
        {
            "first_name": "Ірина",
            "last_name": "Нова",
            "user_id": other.pk,
        },
    )
    assertRedirects(response, reverse("students:account_settings"))
    assert StudentProfile.objects.get(user=user).first_name == "Ірина"
    assert StudentProfile.objects.get(user=other).first_name == "Олена"


def test_settings_errors_preserve_profile(client, student_factory):
    user = student_factory()
    client.force_login(user)
    response = client.post(reverse("students:account_settings"), {"first_name": "", "last_name": "Нова"})
    assert response.status_code == 200
    assert response.context["form"].errors
    assert StudentProfile.objects.get(user=user).first_name == "Олена"


def test_settings_shows_verified_email_and_set_password_for_social_user(client, student_factory):
    user = student_factory()
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    client.force_login(user)
    response = client.get(reverse("students:account_settings"))
    assertContains(response, "Підтверджено")
    assertContains(response, reverse("account_email"))
    assertContains(response, reverse("account_set_password"))


def test_settings_links_to_password_change_when_password_exists(client, student_factory):
    user = student_factory()
    user.set_password("Existing!8-password-2026")
    user.save()
    client.force_login(user)
    response = client.get(reverse("students:account_settings"))
    assertContains(response, reverse("account_change_password"))
    response = client.get(reverse("account_change_password"))
    assertContains(response, "До налаштувань акаунту")


def test_password_can_be_set_and_returns_to_settings(client, student_factory, settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    user = student_factory()
    client.force_login(user)
    password = "New!7-secure-password-2026"
    response = client.post(
        reverse("account_set_password"),
        {
            "password1": password,
            "password2": password,
            "next": reverse("students:account_settings"),
        },
    )
    assertRedirects(response, reverse("students:account_settings"))
    user.refresh_from_db()
    assert user.check_password(password)


def test_email_management_page_and_add_address(client, student_factory, settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    user = student_factory()
    client.force_login(user)
    response = client.get(reverse("account_email"))
    assertContains(response, "Мої адреси")
    response = client.post(reverse("account_email"), {"email": "new-address@example.com", "action_add": ""})
    assert response.status_code == 302
    assert EmailAddress.objects.filter(user=user, email="new-address@example.com", verified=False).exists()
    user.refresh_from_db()
    assert user.email != "new-address@example.com"


def test_profile_settings_require_csrf(student_factory):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(student_factory())
    assert (
        client.post(reverse("students:account_settings"), {"first_name": "Ірина", "last_name": "Нова"}).status_code
        == 403
    )


def test_dashboard_selects_only_members_own_groups(client, owner, group, student_factory):
    from .services import create_group

    second = create_group(owner, name="Друга")
    outsider = student_factory()
    other_group = create_group(outsider, name="Чужа")
    client.force_login(owner)
    response = client.get(reverse("students:dashboard"), {"group": second.pk})
    assert response.context["group"] == second
    assert len(response.context["memberships"]) == 2
    assert client.get(reverse("students:dashboard"), {"group": other_group.pk}).status_code == 403
    assert client.get(reverse("students:dashboard"), {"group": "invalid"}).status_code == 404
