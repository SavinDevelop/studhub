import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def invitation_expiry():
    return timezone.now() + timedelta(days=7)


def avatar_path(instance, filename):
    return f"avatars/{instance.user_id}/{uuid.uuid4().hex}.jpg"


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    first_name = models.CharField("Ім'я", max_length=150, blank=True)
    last_name = models.CharField("Прізвище", max_length=150, blank=True)
    avatar = models.ImageField("Аватарка", upload_to=avatar_path, blank=True)
    google_avatar_url = models.URLField(max_length=2048, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.user.get_username()

    @property
    def avatar_url(self):
        return self.avatar.url if self.avatar else self.google_avatar_url


class StudyGroup(models.Model):
    name = models.CharField("Назва групи", max_length=150)
    description = models.TextField("Заклад освіти / опис", blank=True)
    course = models.PositiveSmallIntegerField(
        "Курс", default=1, validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_study_groups")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.CheckConstraint(condition=models.Q(course__gte=1, course__lte=4), name="group_valid_course"),
        )

    def __str__(self):
        return self.name


class GroupRole(models.TextChoices):
    STUDENT = "student", "Студент"
    DEPUTY = "deputy", "Заступник"


class GroupMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships")
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=GroupRole.choices, default=GroupRole.STUDENT)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (models.UniqueConstraint(fields=["group", "user"], name="unique_group_membership"),)
        ordering = ("joined_at", "pk")

    def __str__(self):
        return f"{self.user} — {self.group}"


class GroupPermission(models.TextChoices):
    INVITE = "can_invite", "Створювати та відкликати запрошення"
    APPROVE = "can_approve", "Схвалювати та відхиляти заявки"
    EDIT_GROUP = "can_edit_group", "Змінювати назву групи"
    REMOVE_MEMBERS = "can_remove_members", "Видаляти звичайних учасників"
    MANAGE_TASKS = "can_manage_tasks", "Створювати та редагувати завдання"
    MANAGE_ACADEMICS = "can_manage_academics", "Керувати навчальним планом"
    VIEW_ANALYTICS = "can_view_analytics", "Переглядати аналітику та матрицю виконання"


class GroupRolePolicy(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="role_policies")
    role = models.CharField(max_length=16, choices=GroupRole.choices)
    can_invite = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_edit_group = models.BooleanField(default=False)
    can_remove_members = models.BooleanField(default=False)
    can_manage_tasks = models.BooleanField(default=False)
    can_manage_academics = models.BooleanField(default=False)
    can_view_analytics = models.BooleanField(default=False)

    class Meta:
        constraints = (models.UniqueConstraint(fields=["group", "role"], name="unique_group_role_policy"),)

    def __str__(self):
        return f"{self.group} — {self.get_role_display()}"


class GroupInvitation(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="invitations")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=invitation_expiry)
    revoked_at = models.DateTimeField(null=True, blank=True)
    email = models.EmailField("Email запрошеного", blank=True)
    max_uses = models.PositiveIntegerField("Ліміт використань", default=20, validators=[MinValueValidator(1)])
    use_count = models.PositiveIntegerField("Використань", default=0)

    class Meta:
        constraints = (
            models.CheckConstraint(condition=models.Q(max_uses__gte=1), name="invitation_positive_limit"),
            models.CheckConstraint(
                condition=models.Q(use_count__lte=models.F("max_uses")), name="invitation_usage_limit"
            ),
        )

    def __str__(self):
        return f"Запрошення до {self.group}"

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now() and self.use_count < self.max_uses


class JoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Очікує розгляду"
        APPROVED = "approved", "Схвалено"
        REJECTED = "rejected", "Відхилено"

    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="join_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_join_requests")
    invitation = models.ForeignKey(GroupInvitation, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reviewed_join_requests",
    )

    class Meta:
        constraints = (models.UniqueConstraint(fields=["group", "user"], name="unique_group_join_request"),)

    def __str__(self):
        return f"{self.user} → {self.group}"
