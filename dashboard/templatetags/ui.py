from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tasks.models import TaskProgress

register = template.Library()

ICON_NAMES = {
    "overview": "layout-dashboard",
    "tasks": "list-todo",
    "calendar": "calendar-days",
    "subjects": "book-open",
    "users": "users-round",
    "chevron": "chevron-down",
    "right": "chevron-right",
    "bell": "bell",
    "collapse": "panel-left-close",
    "file": "file",
    "check": "circle-check",
    "tick": "check",
    "graduation": "graduation-cap",
    "clock": "clock",
    "analytics": "chart-column",
    "settings": "settings",
    "plus": "plus",
    "search": "search",
    "filter": "sliders-horizontal",
    "send": "send",
    "back": "arrow-left",
    "copy": "copy",
    "mail": "mail",
    "arrow": "arrow-right",
    "close": "x",
    "download": "download",
    "check-check": "check-check",
    "semester-calendar": "calendar-days",
    "deadline-calendar": "calendar-days",
    "subject-book": "book-open",
    "notice-bell": "bell",
    "notice-users": "users-round",
}


@lru_cache
def _lucide_svg(name):
    path = Path(settings.BASE_DIR) / "assets" / "icons" / "lucide" / f"{name}.svg"
    # Only bundled, trusted Lucide assets reach this loader.
    return mark_safe(path.read_text().replace("<svg", f'<svg data-lucide="{name}"', 1))


@register.simple_tag
def icon(name, active=False):
    filename = ICON_NAMES.get(name)
    if filename is None:
        return ""
    return format_html('<span class="icon" aria-hidden="true">{}</span>', _lucide_svg(filename))


@register.filter
def status_label(value):
    return dict(TaskProgress.Status.choices).get(value, "Не виконано")


@register.filter
def lookup(mapping, key):
    return mapping.get(key, "not_started")


@register.simple_tag(takes_context=True)
def query(context, **changes):
    params = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)
    return "?" + urlencode(params, doseq=True)


@register.simple_tag
def versioned_static(path):
    """Refresh local assets automatically when their contents change."""
    asset = Path(settings.BASE_DIR) / "assets" / path
    url = static(path)
    if asset.is_file():
        return f"{url}?v={asset.stat().st_mtime_ns}"
    return url
