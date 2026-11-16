"""Group curriculum: semesters, disciplines and optional task topics."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Semester(models.Model):
    group = models.ForeignKey("students.StudyGroup", on_delete=models.CASCADE, related_name="semesters")
    name = models.CharField("Назва", max_length=150)
    academic_year_start = models.PositiveSmallIntegerField(
        "Початок навчального року", blank=True, null=True, validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    starts_on = models.DateField("Дата початку")
    ends_on = models.DateField("Дата завершення", blank=True, null=True)
    is_active = models.BooleanField("Поточний семестр", default=False)

    class Meta:
        ordering = ("-starts_on", "pk")
        constraints = (
            models.CheckConstraint(condition=models.Q(ends_on__gte=models.F("starts_on")), name="semester_valid_dates"),
            models.UniqueConstraint(
                fields=["group"], condition=models.Q(is_active=True), name="one_active_semester_per_group"
            ),
            models.UniqueConstraint(fields=["group", "name"], name="unique_group_semester_name"),
        )
        verbose_name = "Семестр"
        verbose_name_plural = "Семестри"

    def __str__(self):
        return f"{self.group} — {self.name}"

    @property
    def academic_year(self):
        return f"{self.academic_year_start} / {self.academic_year_start + 1}" if self.academic_year_start else ""


class Subject(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField("Назва предмета", max_length=255)
    description = models.TextField("Опис", blank=True)
    teacher_name = models.CharField("ПІБ викладача", max_length=255)
    teacher_email = models.EmailField("Email викладача", blank=True)
    teacher_phone = models.CharField("Телефон", max_length=40, blank=True)
    teacher_contact = models.CharField("Telegram / інший контакт", max_length=255, blank=True)
    is_archived = models.BooleanField("В архіві", default=False)

    class Meta:
        ordering = ("name", "pk")
        constraints = (models.UniqueConstraint(fields=["semester", "name"], name="unique_semester_subject_name"),)
        verbose_name = "Предмет"
        verbose_name_plural = "Предмети"

    def __str__(self):
        return self.name

    @property
    def group(self):
        return self.semester.group


class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField("Тема", max_length=255)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = (models.UniqueConstraint(fields=["subject", "name"], name="unique_subject_topic_name"),)
        verbose_name = "Тема"
        verbose_name_plural = "Теми"

    def __str__(self):
        return self.name
