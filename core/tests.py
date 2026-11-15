import re
from urllib.parse import urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

pytestmark = pytest.mark.django_db


@pytest.fixture
def password():
    return "StudyHub!9-secure-2026"


@pytest.fixture
def user(django_user_model, password):
    return django_user_model.objects.create_user(
        username="student",
        email="student@example.com",
        password=password,
    )


@pytest.fixture(autouse=True)
def email_backend(settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@pytest.fixture
def login(client, user, password):
    def submit(**overrides):
        return client.post(
            reverse("account_login"),
            {"login": user.email, "password": password, **overrides},
        )

    return submit


@pytest.fixture
def signup(client, password):
    def submit(**overrides):
        return client.post(
            reverse("account_signup"),
            {"email": "new@example.com", "password1": password, "password2": password, **overrides},
        )

    return submit


@pytest.mark.parametrize("name", ["account_login", "account_signup", "account_reset_password"])
def test_auth_pages_render(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 200
    assertContains(response, 'name="csrfmiddlewaretoken"')


def test_signup_creates_user_and_session(client, signup, password):
    response = signup()
    assert response.status_code == 302
    user = get_user_model().objects.get(email="new@example.com")
    assert user.check_password(password)
    assert user.password != password
    assert client.session["_auth_user_id"] == str(user.pk)


def test_signup_destination_exists(client, signup):
    response = signup()
    assert response.status_code == 302
    destination = client.get(response.url, follow=True)
    assert destination.status_code == 200
    assert destination.resolver_match.view_name == "students:profile"


@pytest.mark.parametrize(
    "fields",
    [
        {"email": "invalid"},
        {"password2": "different-password"},
        {"password1": "123", "password2": "123"},
        {"email": ""},
    ],
)
def test_signup_rejects_invalid_fields(client, signup, fields):
    response = signup(**fields)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert not get_user_model().objects.filter(email="new@example.com").exists()
    assert "_auth_user_id" not in client.session


def test_duplicate_email_does_not_create_another_user(client, signup, user):
    signup(email=user.email.upper())
    assert get_user_model().objects.filter(email__iexact=user.email).count() == 1
    assert "_auth_user_id" not in client.session


def test_login_creates_session(client, login, user):
    response = login()
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_login_destination_exists(client, login):
    response = login()
    assert response.status_code == 302
    destination = client.get(response.url, follow=True)
    assert destination.status_code == 200
    assert destination.resolver_match.view_name == "students:profile"


def test_login_accepts_email_case_insensitively(client, login, user):
    login(login=user.email.upper())
    assert client.session["_auth_user_id"] == str(user.pk)


@pytest.mark.parametrize("fields", [{"password": "wrong"}, {"login": "missing@example.com"}])
def test_login_rejects_invalid_credentials(client, login, fields):
    response = login(**fields)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert "_auth_user_id" not in client.session


def test_inactive_user_cannot_login(client, login, user):
    user.is_active = False
    user.save(update_fields=["is_active"])
    login()
    assert "_auth_user_id" not in client.session


def test_external_redirect_is_rejected(login):
    response = login(next="https://attacker.example/steal")
    assert response.status_code == 302
    assert urlsplit(response.url).netloc == ""


def test_local_redirect_is_preserved(login):
    response = login(next="/")
    assertRedirects(response, "/", fetch_redirect_response=False)


def test_logout_requires_post_and_clears_session(client, login):
    login()
    response = client.get(reverse("account_logout"))
    assert response.status_code == 200
    assert "_auth_user_id" in client.session
    response = client.post(reverse("account_logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("name", ["account_login", "account_signup", "account_logout", "account_reset_password"])
def test_auth_posts_require_csrf(name):
    client = Client(enforce_csrf_checks=True)
    assert client.post(reverse(name), {}).status_code == 403


def test_password_reset_changes_password_and_token_cannot_be_reused(client, user, login, password, mailoutbox):
    response = client.post(reverse("account_reset_password"), {"email": user.email})
    assertRedirects(response, reverse("account_reset_password_done"))
    assert len(mailoutbox) == 1
    reset_url = re.search(r"https?://[^\s]+/accounts/password/reset/key/[^\s]+", mailoutbox[0].body)
    assert reset_url is not None
    path = urlsplit(reset_url.group()).path
    response = client.get(path, follow=True)
    assert response.status_code == 200
    action = response.context["action_url"]
    new_password = "Replacement!8-study-2026"
    response = client.post(action, {"password1": new_password, "password2": new_password})
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password(new_password)
    assert not user.check_password(password)
    login(password=new_password)
    assert client.session["_auth_user_id"] == str(user.pk)
    client.logout()
    response = client.get(path, follow=True)
    assert response.context["token_fail"]


def test_password_reset_unknown_email_does_not_disclose_account(client, mailoutbox):
    response = client.post(reverse("account_reset_password"), {"email": "unknown@example.com"})
    assertRedirects(response, reverse("account_reset_password_done"))
    for message in mailoutbox:
        assert "/accounts/password/reset/key/" not in message.body
    assert not get_user_model().objects.filter(email="unknown@example.com").exists()


def test_google_login_starts_oauth(client):
    response = client.post(reverse("google_login"))
    assert response.status_code == 302
    destination = urlsplit(response.url)
    assert destination.hostname == "accounts.google.com"
    assert "state=" in destination.query
    assert "code_challenge=" in destination.query
