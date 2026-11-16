from django import forms
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        cleaned = [super(MultipleFileField, self).clean(item, initial) for item in files]
        if any(item.size > 10 * 1024 * 1024 for item in cleaned):
            raise forms.ValidationError("Кожен файл має бути не більше 10 МБ.")
        return cleaned


class URLListWidget(forms.TextInput):
    def value_from_datadict(self, data, files, name):
        return data.getlist(name) if hasattr(data, "getlist") else data.get(name, [])

    def id_for_label(self, id_):
        return f"{id_}_0" if id_ else ""

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(value, str):
            value = value.split()
        context = self.get_context(name, value, attrs)
        context["values"] = value or [""]
        return mark_safe(render_to_string("ui/url_list_widget.html", context))


class URLListField(forms.Field):
    widget = URLListWidget

    def clean(self, value):
        values = value if isinstance(value, (list, tuple)) else [value or ""]
        field = forms.URLField(max_length=2048, validators=[])
        urls = [field.clean(url) for item in values for url in item.split() if url.strip()]
        # Explicit schemes match the material and submission link models.
        if any(not url.lower().startswith(("https://", "http://")) for url in urls):
            raise forms.ValidationError("Вкажіть посилання з http:// або https://.")
        if len(urls) != len(set(urls)):
            raise forms.ValidationError("Посилання не повинні повторюватися.")
        return urls
