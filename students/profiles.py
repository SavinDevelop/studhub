from io import BytesIO
from urllib.parse import urlsplit

from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import StudentProfile

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000


def get_profile(user):
    """Google data only pre-fills an unconfirmed profile, never overwrites confirmed data."""
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    if profile.completed_at:
        return profile
    account = SocialAccount.objects.filter(user=user, provider="google").first()
    data = account.extra_data if account else {}
    profile.first_name = profile.first_name or user.first_name or data.get("given_name", "")
    profile.last_name = profile.last_name or user.last_name or data.get("family_name", "")
    picture = data.get("picture", "")
    if isinstance(picture, str) and urlsplit(picture).scheme == "https":
        profile.google_avatar_url = profile.google_avatar_url or picture
    return profile


def _prepare_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise ValidationError({"avatar": "Максимальний розмір аватарки — 5 МБ."})
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError({"avatar": "Оберіть JPEG, PNG або WebP."})
            if image.width * image.height > MAX_AVATAR_PIXELS:
                raise ValidationError({"avatar": "Зображення завелике: максимум 16 мегапікселів."})
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((512, 512))
            output = BytesIO()
            image.save(output, format="JPEG", quality=85)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValidationError({"avatar": "Не вдалося прочитати зображення."}) from exc
    finally:
        upload.seek(0)
    return ContentFile(output.getvalue(), name="avatar.jpg")


@transaction.atomic
def complete_profile(user, *, first_name, last_name, avatar=None, remove_avatar=False):
    profile = get_profile(user)
    profile.first_name = first_name.strip()
    profile.last_name = last_name.strip()
    errors = {}
    for field in ("first_name", "last_name"):
        if not getattr(profile, field):
            errors[field] = "Заповніть це поле."
    if errors:
        raise ValidationError(errors)
    profile.completed_at = profile.completed_at or timezone.now()
    if remove_avatar:
        profile.avatar = ""
        profile.google_avatar_url = ""
    # Validate before writing an image to storage.
    profile.full_clean()
    if avatar:
        profile.avatar = _prepare_avatar(avatar)
    profile.save()
    user.first_name = profile.first_name
    user.last_name = profile.last_name
    user.save(update_fields=["first_name", "last_name"])
    return profile
