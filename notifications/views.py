from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .services import list_notifications, mark_read


@login_required
def inbox(request):
    unread = request.GET.get("state") == "unread"
    notices = list_notifications(request.user, unread_only=unread)
    return render(
        request,
        "notifications/inbox.html",
        {
            "page": Paginator(notices, 15).get_page(request.GET.get("page")),
            "state": "unread" if unread else "all",
            "total": list_notifications(request.user).count(),
            "page_title": "Сповіщення",
            "nav": "notifications",
        },
    )


@login_required
@require_POST
def read(request, pk=None):
    notice = get_object_or_404(list_notifications(request.user), pk=pk) if pk else None
    mark_read(request.user, pk)
    if notice:
        if notice.task_id and notice.group.memberships.filter(user=request.user).exists():
            return redirect("tasks:detail", pk=notice.task_id)
        if notice.invitation_id:
            return redirect("students:invitation", token=notice.invitation.token)
        if notice.group.memberships.filter(user=request.user).exists():
            return redirect("students:group", group_id=notice.group_id)
    return redirect("notifications:inbox")
