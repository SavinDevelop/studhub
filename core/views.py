from typing import TYPE_CHECKING

from django.shortcuts import render

if TYPE_CHECKING:
    from django.http.request import HttpRequest


def view_home(request: HttpRequest):
    return render(request, "home.html", {})


def local_media(request, path):
    """Development avatar delivery; assignment files require the authorized download view."""
    from pathlib import PurePosixPath

    from django.conf import settings
    from django.http import Http404
    from django.views.static import serve

    parts = PurePosixPath(path).parts
    if not parts or parts[0] != "avatars" or ".." in parts:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
