from typing import ClassVar

from django import forms
from django.core.validators import URLValidator

from academics.models import Subject, Topic

from .models import Task


class TaskForm(forms.ModelForm):
    attachment = forms.FileField(label="Додати файл", required=False)
    attachment_url = forms.URLField(
        label="Посилання на матеріали",
        required=False,
        max_length=2048,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    submission_urls = forms.CharField(
        label="Посилання для здачі (по одному в рядку)", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = Task
        fields = ("title", "description", "work_type", "subject", "deadline", "topic", "is_required", "priority")
        widgets: ClassVar = {
            "title": forms.TextInput(attrs={"placeholder": "Наприклад: Самостійна робота №5"}),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Додайте опис, матеріали та посилання…"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "priority": forms.RadioSelect,
        }

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.filter(semester__group=group).select_related("semester")
        self.fields["subject"].required = True
        self.fields["topic"].queryset = Topic.objects.filter(subject__semester__group=group).select_related("subject")
        self.fields["topic"].empty_label = "Без теми"
        if self.instance.pk:
            self.fields["submission_urls"].initial = "\n".join(
                self.instance.submission_links.values_list("url", flat=True)
            )

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment and attachment.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Файл має бути не більше 10 МБ.")
        return attachment

    def clean_submission_urls(self):
        urls = [url.strip() for url in self.cleaned_data["submission_urls"].splitlines() if url.strip()]
        field = forms.URLField(max_length=2048)
        return [field.clean(url) for url in urls]
