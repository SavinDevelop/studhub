from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        TASK_CREATED = "task_created", "Нове завдання"
        TASK_UPDATED = "task_updated", "Оновлення завдання"
        DEADLINE = "deadline", "Наближення дедлайну"
        MENTION = "mention", "Згадка у коментарі"
        INVITATION = "invitation", "Запрошення до групи"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField("Тип", max_length=20, choices=Kind.choices)
    title = models.CharField("Заголовок", max_length=255)
    body = models.TextField("Текст", blank=True)
    group = models.ForeignKey("students.StudyGroup", on_delete=models.CASCADE, related_name="notifications")
    task = models.ForeignKey(
        "tasks.Task", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True
    )
    comment = models.ForeignKey(
        "tasks.TaskComment", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True
    )
    invitation = models.ForeignKey(
        "students.GroupInvitation", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField("Прочитано", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = (models.Index(fields=["recipient", "read_at", "-created_at"], name="notification_inbox_idx"),)
        verbose_name = "Сповіщення"
        verbose_name_plural = "Сповіщення"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.task_id and (self.task.group is None or self.task.group.pk != self.group_id):
            raise ValidationError({"task": "Завдання повинно належати групі сповіщення."})
        if self.comment_id and self.comment.task_id != self.task_id:
            raise ValidationError({"comment": "Коментар повинен належати завданню сповіщення."})
        if self.invitation_id and self.invitation.group_id != self.group_id:
            raise ValidationError({"invitation": "Запрошення повинно належати групі сповіщення."})
