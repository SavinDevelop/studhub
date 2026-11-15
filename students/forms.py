from typing import ClassVar

from django import forms

from .models import GroupRolePolicy


class ProfileForm(forms.Form):
    first_name = forms.CharField(label="Ім'я", max_length=150)
    last_name = forms.CharField(label="Прізвище", max_length=150)
    avatar = forms.FileField(label="Нова аватарка (JPEG, PNG, WebP, до 5 МБ)", required=False)
    remove_avatar = forms.BooleanField(label="Видалити поточну аватарку", required=False)


class GroupForm(forms.Form):
    name = forms.CharField(label="Назва групи", max_length=150)


class RolePolicyForm(forms.ModelForm):
    class Meta:
        model = GroupRolePolicy
        fields = (
            "can_invite",
            "can_approve",
            "can_edit_group",
            "can_remove_members",
            "can_manage_tasks",
            "can_manage_academics",
            "can_view_analytics",
        )
        labels: ClassVar[dict[str, str]] = {
            "can_invite": "Створювати та відкликати запрошення",
            "can_approve": "Схвалювати та відхиляти заявки",
            "can_edit_group": "Змінювати назву групи",
            "can_remove_members": "Видаляти звичайних учасників",
            "can_manage_tasks": "Створювати та редагувати завдання",
            "can_manage_academics": "Керувати навчальним планом",
            "can_view_analytics": "Переглядати аналітику та матрицю виконання",
        }


class InvitationForm(forms.Form):
    email = forms.EmailField(label="Email учасника", widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))
    max_uses = forms.IntegerField(label="Ліміт використань", min_value=1, initial=1, widget=forms.HiddenInput)
