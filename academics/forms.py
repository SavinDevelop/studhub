from typing import ClassVar

from django import forms

from .models import Semester, Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = (
            "name",
            "semester",
            "description",
            "teacher_name",
            "teacher_email",
            "teacher_phone",
            "teacher_contact",
            "is_archived",
        )
        widgets: ClassVar = {
            "description": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Вкажіть основні теми, цілі навчання та особливості дисципліни…"}
            )
        }

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["semester"].queryset = Semester.objects.filter(group=group)
        self.fields["teacher_name"].widget.attrs["placeholder"] = "Введіть ім'я та прізвище"
        self.fields["teacher_phone"].widget.attrs["placeholder"] = "+380 …"
        self.fields["teacher_contact"].widget.attrs["placeholder"] = "@username або посилання"


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ("name", "academic_year_start", "starts_on", "ends_on")
        widgets: ClassVar = {
            "starts_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ends_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class CourseForm(forms.Form):
    course = forms.TypedChoiceField(
        label="Курс навчання", choices=[(value, f"{value} курс") for value in range(1, 5)], coerce=int
    )


class TopicForm(forms.Form):
    name = forms.CharField(
        label="Назва теми", max_length=255, widget=forms.TextInput(attrs={"placeholder": "Додати тему предмета"})
    )
