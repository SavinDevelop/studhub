from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import StudentProfile


class ProfileCompletionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        exempt = ("/accounts/", "/admin/", settings.STATIC_URL, settings.MEDIA_URL)
        if (
            request.user.is_authenticated
            and request.path != reverse("students:profile")
            and not request.path.startswith(exempt)
            and not StudentProfile.objects.filter(user=request.user, completed_at__isnull=False).exists()
        ):
            return redirect(f"{reverse('students:profile')}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)
