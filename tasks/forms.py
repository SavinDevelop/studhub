from typing import ClassVar

from django import forms

from academics.models import Subject

from .models import Task
from .widgets import MultipleFileField, MultipleFileInput, URLListField, URLListWidget


class TaskForm(forms.ModelForm):
    topic_name = forms.CharField(
        label="Тема",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Введіть назву теми"}),
    )
    attachment = MultipleFileField(
        label="Додати файли",
        required=False,
        widget=MultipleFileInput(attrs={"class": "visually-hidden-file"}),
    )
    attachment_url = URLListField(
        label="Посилання на матеріали",
        required=False,
        widget=URLListWidget(attrs={"url_label": "Посилання на матеріали"}),
    )
    submission_urls = URLListField(
        label="Посилання для здачі",
        required=False,
        widget=URLListWidget(attrs={"url_label": "Посилання для здачі"}),
    )

    class Meta:
        model = Task
        fields = ("title", "description", "work_type", "subject", "starts_on", "deadline", "is_required", "priority")
        labels: ClassVar = {"subject": "Предмет"}
        widgets: ClassVar = {
            "title": forms.TextInput(attrs={"placeholder": "Наприклад: Самостійна робота №5"}),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Додайте опис, матеріали та посилання…"}),
            "starts_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "priority": forms.RadioSelect,
        }

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.filter(semester__group=group).select_related("semester")
        self.fields["subject"].required = True
        self.fields["topic_name"].initial = self.instance.topic.name if self.instance.topic_id else ""
        if self.instance.pk:
            self.fields["submission_urls"].initial = list(self.instance.submission_links.values_list("url", flat=True))
            self.fields["attachment_url"].initial = list(
                self.instance.attachments.exclude(url="").values_list("url", flat=True)
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("subject") and self.instance.subject_id != cleaned["subject"].pk:
            self.instance.topic = None
        return cleaned
