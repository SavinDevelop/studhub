import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models


class Task(models.Model):
    class WorkType(models.TextChoices):
        INDEPENDENT = "independent", "Самостійна робота"
        PRACTICAL = "practical", "Практична робота"
        LABORATORY = "laboratory", "Лабораторна робота"
        SEMINAR = "seminar", "Семінар"
        TEST = "test", "Тест"
        MODULE = "module", "Модульна контрольна робота"
        OTHER = "other", "Інше"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Звичайний"
        HIGH = "high", "Високий"

    title = models.CharField("Назва", max_length=255)
    legacy_topic = models.CharField("Тема до перенесення", max_length=255, blank=True)
    legacy_subject = models.CharField("Предмет до перенесення", max_length=255, blank=True)
    subject = models.ForeignKey(
        "academics.Subject", on_delete=models.PROTECT, related_name="tasks", null=True, blank=True
    )
    topic = models.ForeignKey("academics.Topic", on_delete=models.SET_NULL, related_name="tasks", null=True, blank=True)
    work_type = models.CharField("Тип роботи", max_length=20, choices=WorkType.choices, default=WorkType.INDEPENDENT)
    priority = models.CharField("Пріоритет", max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks"
    )
    deadline = models.DateTimeField("Дедлайн", db_index=True)
    is_required = models.BooleanField("Обов'язкове", default=True)
    description = models.TextField("Опис", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("deadline", "pk")
        verbose_name = "Завдання"
        verbose_name_plural = "Завдання"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if not self.subject_id and not self.legacy_subject:
            raise ValidationError({"subject": "Оберіть предмет."})
        if self.topic_id and self.topic.subject_id != self.subject_id:
            raise ValidationError({"topic": "Тема повинна належати предмету завдання."})

    @property
    def group(self):
        return self.subject.group if self.subject_id else None

    @property
    def is_overdue(self):
        from django.utils import timezone

        return self.deadline < timezone.now()


class TaskProgress(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Не виконано"
        IN_PROGRESS = "in_progress", "У процесі"
        COMPLETED = "completed", "Виконано"
        GRADED = "graded", "Оцінено"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="progress")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_progress")
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (models.UniqueConstraint(fields=["task", "user"], name="unique_student_task_progress"),)
        verbose_name = "Прогрес студента"
        verbose_name_plural = "Прогрес студентів"

    def __str__(self):
        return f"{self.user} — {self.task}: {self.get_status_display()}"

    @property
    def is_overdue(self):
        return self.status not in (self.Status.COMPLETED, self.Status.GRADED) and self.task.is_overdue

    def clean(self):
        super().clean()
        if self.task_id and self.user_id:
            group = self.task.group
            if group is None or not group.memberships.filter(user_id=self.user_id).exists():
                raise ValidationError({"user": "Студент повинен бути учасником групи завдання."})


def attachment_path(instance, filename):
    # Storage names do not trust or expose the user-supplied filename.
    return f"tasks/{instance.task_id}/{uuid.uuid4().hex}"


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField("Назва", max_length=255)
    file = models.FileField("Файл", upload_to=attachment_path, blank=True)
    url = models.URLField(
        "Посилання", max_length=2048, blank=True, validators=[URLValidator(schemes=["http", "https"])]
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = (
            models.CheckConstraint(
                condition=(models.Q(file="") & ~models.Q(url="")) | (~models.Q(file="") & models.Q(url="")),
                name="attachment_file_or_url",
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if bool(self.file) == bool(self.url):
            raise ValidationError("Вкажіть файл або посилання.")


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_comments"
    )
    body = models.TextField("Коментар")
    mentions = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="task_comment_mentions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return self.body[:80]


class SubmissionLink(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="submission_links")
    url = models.URLField("Посилання для здачі", max_length=2048, validators=[URLValidator(schemes=["http", "https"])])

    class Meta:
        ordering = ("pk",)
        constraints = (models.UniqueConstraint(fields=["task", "url"], name="unique_task_submission_url"),)
        verbose_name = "Посилання для здачі"
        verbose_name_plural = "Посилання для здачі"

    def __str__(self):
        return self.url
