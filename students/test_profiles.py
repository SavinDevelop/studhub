from io import BytesIO

import pytest
from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from .models import StudentProfile
from .profiles import MAX_AVATAR_BYTES, complete_profile, get_profile

pytestmark = pytest.mark.django_db


def test_google_data_is_prefilled_but_requires_confirmation(student_factory):
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
    profile = get_profile(user)
    assert profile.first_name == "Олена"
    assert profile.last_name == "Коваль"
    assert profile.avatar_url == "https://example.com/photo.jpg"
    assert profile.completed_at is None
    assert StudentProfile.objects.get(user=user).completed_at is None
    profile = complete_profile(user, first_name="Олена", last_name="Нова")
    assert profile.completed_at is not None
    assert profile.last_name == "Нова"
    assert profile.google_avatar_url == "https://example.com/photo.jpg"


def test_confirmed_profile_is_not_overwritten_by_google(student_factory):
    user = student_factory()
    SocialAccount.objects.create(
        user=user,
        provider="google",
        uid="123",
        extra_data={
            "given_name": "Інше",
            "family_name": "Прізвище",
            "picture": "https://example.com/photo.jpg",
        },
    )
    profile = get_profile(user)
    assert profile.first_name == "Олена"
    assert profile.google_avatar_url == ""


@pytest.mark.parametrize(("field", "value"), [("first_name", " "), ("last_name", ""), ("first_name", "x" * 151)])
def test_names_are_required_and_validated(student_factory, field, value):
    user = student_factory(complete=False)
    fields = {"first_name": "Олена", "last_name": "Коваль", field: value}
    with pytest.raises(ValidationError):
        complete_profile(user, **fields)
    assert not StudentProfile.objects.filter(user=user, completed_at__isnull=False).exists()


def test_names_are_trimmed_and_synced_to_auth_user(student_factory):
    user = student_factory(complete=False)
    profile = complete_profile(user, first_name=" Олена ", last_name=" Коваль ")
    user.refresh_from_db()
    assert profile.first_name == user.first_name == "Олена"
    assert profile.last_name == user.last_name == "Коваль"


def test_avatar_is_resized_reencoded_and_metadata_removed(student_factory):
    user = student_factory()
    output = BytesIO()
    Image.new("RGB", (1024, 768), color="red").save(output, format="PNG")
    upload = SimpleUploadedFile("unsafe-name.png", output.getvalue(), content_type="image/png")
    profile = complete_profile(user, first_name="Олена", last_name="Коваль", avatar=upload)
    assert profile.avatar.name.endswith(".jpg")
    assert "unsafe-name" not in profile.avatar.name
    with profile.avatar.open("rb") as stored, Image.open(stored) as image:
        assert image.format == "JPEG"
        assert image.size == (512, 384)
        assert not image.getexif()


@pytest.mark.parametrize("content", [b"not an image", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'])
def test_invalid_avatar_preserves_existing_profile(student_factory, content):
    user = student_factory()
    with pytest.raises(ValidationError):
        complete_profile(user, first_name="Інше", last_name="Коваль", avatar=SimpleUploadedFile("photo.jpg", content))
    assert get_profile(user).first_name == "Олена"


def test_avatar_size_limit(student_factory):
    user = student_factory()
    upload = SimpleUploadedFile("large.jpg", b"x" * (MAX_AVATAR_BYTES + 1))
    with pytest.raises(ValidationError, match="5 МБ"):
        complete_profile(user, first_name="Олена", last_name="Коваль", avatar=upload)


def test_avatar_pixel_limit(student_factory):
    user = student_factory()
    output = BytesIO()
    Image.new("1", (4001, 4000)).save(output, format="PNG")
    with pytest.raises(ValidationError, match="16 мегапікселів"):
        complete_profile(
            user, first_name="Олена", last_name="Коваль", avatar=SimpleUploadedFile("photo.png", output.getvalue())
        )


def test_google_avatar_can_be_removed(student_factory):
    user = student_factory()
    StudentProfile.objects.filter(user=user).update(google_avatar_url="https://example.com/photo.jpg")
    profile = complete_profile(user, first_name="Олена", last_name="Коваль", remove_avatar=True)
    assert profile.avatar_url == ""


def test_non_https_google_avatar_ignored(student_factory):
    user = student_factory(complete=False)
    SocialAccount.objects.create(user=user, provider="google", uid="123", extra_data={"picture": "javascript:alert(1)"})
    assert get_profile(user).avatar_url == ""
