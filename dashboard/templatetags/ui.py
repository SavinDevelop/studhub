import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

from tasks.models import TaskProgress

register = template.Library()

ICON_NAMES = {
    "overview": "imgLucideLayoutDashboard",
    "tasks": "imgLucideListTodo",
    "calendar": "imgLucideCalendarDays",
    "subjects": "imgLucideBookOpen",
    "users": "imgLucideUsersRound",
    "chevron": "imgLucideChevronDown",
    "right": "imgLucideChevronRight",
    "bell": "imgLucideBell",
    "collapse": "imgLucidePanelLeftClose",
    "file": "imgLucideFile",
    "check": "imgLucideCircleCheck",
    "tick": "imgLucideCheck",
    "graduation": "imgLucideGraduation",
    "clock": "imgLucideClock",
    "analytics": "imgLucideChart",
    "settings": "imgLucideSettings",
    "plus": "imgLucidePlus",
    "search": "imgLucideSearch",
    "filter": "imgLucideSliders",
    "send": "imgLucideSend",
    "back": "imgLucideArrowLeft",
    "copy": "imgLucideCopy",
    "mail": "imgLucideMail",
    "arrow": "imgLucideArrow",
    "close": "imgLucideX",
    "download": "imgLucideDownload",
}
SCREENS = {
    "overview": "67:25",
    "tasks": "67:209",
    "calendar": "67:495",
    "subjects": "67:773",
    "users": "67:656",
    "analytics": "67:3836",
    "settings": "67:3428",
}


@lru_cache
def asset_manifest():
    path = Path(settings.BASE_DIR) / "assets/figma/manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


@register.simple_tag
def icon(name, active=False):
    manifest = asset_manifest()
    key = ICON_NAMES.get(name, name)
    inactive = {"overview": "67:209", "analytics": "67:3428", "settings": "67:3836"}
    slots = {
        "semester-calendar": ("67:209", "imgLucideCalendarDays1"),
        "deadline-calendar": ("67:365", "imgLucideCalendarDays1"),
        "subject-book": ("67:773", "imgLucideBook"),
        "notice-bell": ("67:1026", "imgLucideBell1"),
        "notice-users": ("67:1026", "imgLucideUsers"),
    }
    screen = SCREENS.get(name) if active else inactive.get(name, "67:25")
    if name in slots:
        screen, key = slots[name]
    filename = manifest.get(screen, {}).get(key)
    filename = filename or next((items[key] for items in manifest.values() if key in items), None)
    if not filename:
        return ""
    return format_html(
        '<span class="icon" aria-hidden="true"><img src="{}" alt=""></span>', static(f"figma/{filename}")
    )


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
