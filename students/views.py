from functools import wraps

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import services
from .forms import GroupForm, ProfileForm, RolePolicyForm
from .models import GroupPermission, GroupRole, JoinRequest
from .profiles import complete_profile, get_profile


def _service_errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ObjectDoesNotExist as exc:
            raise Http404 from exc
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("students:dashboard")

    return wrapped


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    return _profile_response(request, "students/profile.html", "students:dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request):
    return _profile_response(request, "students/account_settings.html", "students:account_settings")


def _profile_response(request, template_name, default_destination):
    student = get_profile(request.user)
    destination = request.POST.get("next", request.GET.get("next", ""))
    if not url_has_allowed_host_and_scheme(
        destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) or destination.split("?")[0] == reverse("students:profile"):
        destination = reverse(default_destination)
    form = ProfileForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial={"first_name": student.first_name, "last_name": student.last_name},
    )
    if request.method == "POST" and form.is_valid():
        try:
            complete_profile(request.user, **form.cleaned_data)
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                form.add_error(None, exc)
        else:
            messages.success(request, "Профіль збережено.")
            return redirect(destination)
    return render(
        request,
        template_name,
        {
            "nav": "profile",
            "page_title": "Налаштування",
            "form": form,
            "student": student,
            "next": destination,
            "has_password": request.user.has_usable_password(),
            "primary_email": EmailAddress.objects.filter(user=request.user, primary=True).first(),
            "google_connected": SocialAccount.objects.filter(user=request.user, provider="google").exists(),
        },
    )


@login_required
@_service_errors
def dashboard(request):
    from dashboard.selectors import percent, semester_tasks, task_stats
    from dashboard.workspace import workspace_for

    workspace = workspace_for(request)
    group = workspace["group"]
    tasks = semester_tasks(request.user, workspace)
    stats = task_stats(tasks)
    stats["percent"] = percent(stats["required_done"], stats["required"])
    can_review = workspace["permissions"][GroupPermission.APPROVE]
    return render(
        request,
        "students/dashboard.html",
        {
            "group": group,
            "student": get_profile(request.user),
            "role": workspace["role"],
            "stats": stats,
            "upcoming": tasks[:4],
            "memberships": workspace["memberships"],
            "member_count": group.memberships.count() if group else 0,
            "pending_reviews": group.join_requests.filter(status=JoinRequest.Status.PENDING).count()
            if can_review
            else 0,
            "can_review": can_review,
            "join_requests": request.user.group_join_requests.select_related("group").order_by("-created_at"),
            "nav": "overview",
            "page_title": "Мій огляд",
        },
    )


@login_required
@require_GET
def new_group(request):
    return render(request, "students/new_group.html", {"form": GroupForm()})


@login_required
@require_POST
@_service_errors
def create_group(request):
    form = GroupForm(request.POST)
    if not form.is_valid():
        return render(request, "students/new_group.html", {"form": form}, status=400)
    group = services.create_group(request.user, **form.cleaned_data)
    return redirect("students:group", group_id=group.pk)


@login_required
@_service_errors
def group_detail(request, group_id):
    group = services.get_group(request.user, group_id)
    request.session["active_group"] = group.pk
    permissions = {
        permission.value: services.has_group_permission(request.user, group, permission)
        for permission in GroupPermission
    }
    members = group.memberships.select_related("user__student_profile")
    search = request.GET.get("q", "").strip()
    if search:
        from django.db.models import Q

        members = members.filter(
            Q(user__student_profile__first_name__icontains=search)
            | Q(user__student_profile__last_name__icontains=search)
            | Q(user__email__icontains=search)
        )
    role_filter = request.GET.get("role", "")
    if role_filter == "owner":
        members = members.filter(user_id=group.owner_id)
    elif role_filter in GroupRole.values:
        members = members.filter(role=role_filter).exclude(user_id=group.owner_id)
    context = {
        "group": group,
        "nav": "members",
        "page_title": "Учасники групи",
        "members": members,
        "permissions": permissions,
        "is_owner": group.owner_id == request.user.pk,
        "join_requests": group.join_requests.filter(status=JoinRequest.Status.PENDING).select_related(
            "user__student_profile"
        )
        if permissions[GroupPermission.APPROVE]
        else [],
    }
    return render(request, "students/group.html", context)


@login_required
@require_POST
@_service_errors
def update_group(request, group_id):
    form = GroupForm(request.POST)
    if not form.is_valid():
        raise ValidationError("Вкажіть коректну назву групи.")
    services.update_group(request.user, group_id, **form.cleaned_data)
    return redirect("students:group", group_id=group_id)


@login_required
@require_POST
@_service_errors
def create_invitation(request, group_id):
    services.create_invitation(request.user, group_id)
    if request.POST.get("return") == "invitations":
        return redirect("students:invitations", group_id=group_id)
    return redirect("students:group", group_id=group_id)


@login_required
@require_POST
@_service_errors
def revoke_invitation(request, group_id, invitation_id):
    group = services.get_group(request.user, group_id)
    group.invitations.get(pk=invitation_id)
    services.revoke_invitation(request.user, invitation_id)
    return redirect("students:group", group_id=group_id)


@login_required
@require_http_methods(["GET", "POST"])
@_service_errors
def invitation(request, token):
    invite = services.get_invitation(token)
    if request.method == "POST":
        services.request_to_join(request.user, token)
        messages.success(request, "Заявку надіслано. Дочекайтеся схвалення у групі.")
        return redirect("students:dashboard")
    return render(request, "students/invitation.html", {"invitation": invite})


@login_required
@require_POST
@_service_errors
def review_request(request, group_id, request_id, decision):
    group = services.get_group(request.user, group_id)
    group.join_requests.get(pk=request_id)
    if decision not in {"approve", "reject"}:
        raise Http404
    services.review_join_request(request.user, request_id, approve=decision == "approve")
    return redirect("students:group", group_id=group_id)


@login_required
@require_POST
@_service_errors
def member_role(request, group_id, member_id):
    services.set_member_role(request.user, group_id, member_id=member_id, role=request.POST.get("role"))
    return redirect("students:group", group_id=group_id)


@login_required
@require_POST
@_service_errors
def remove_member(request, group_id, member_id):
    services.remove_member(request.user, group_id, member_id=member_id)
    return redirect("students:group", group_id=group_id)


@login_required
@require_POST
@_service_errors
def leave_group(request, group_id):
    services.leave_group(request.user, group_id)
    return redirect("students:dashboard")


@login_required
@require_POST
@_service_errors
def role_permissions(request, group_id, role):
    if role not in GroupRole.values:
        raise Http404
    form = RolePolicyForm(request.POST)
    if not form.is_valid():
        raise ValidationError("Некоректні налаштування прав.")
    services.set_role_permissions(request.user, group_id, role=role, **form.cleaned_data)
    if request.POST.get("return") == "permissions":
        messages.success(request, "Права доступу збережено.")
        return redirect("students:group_permissions", group_id=group_id)
    return redirect("students:group", group_id=group_id)


@login_required
def groups(request):
    from dashboard.workspace import workspace_for

    return render(
        request,
        "students/groups.html",
        {
            "memberships": workspace_for(request)["memberships"],
            "join_requests": request.user.group_join_requests.select_related("group"),
            "nav": "groups",
            "page_title": "Мої групи",
        },
    )


@login_required
@require_POST
def join_group(request):
    import uuid
    from urllib.parse import urlsplit

    supplied = request.POST.get("invitation", "").strip()
    token = urlsplit(supplied).path.rstrip("/").split("/")[-1]
    try:
        token = uuid.UUID(token)
    except ValueError:
        messages.error(request, "Вкажіть дійсне посилання-запрошення.")
        return redirect("students:groups")
    return redirect("students:invitation", token=token)


@login_required
@_service_errors
def invitations(request, group_id):
    from .forms import InvitationForm
    from .models import GroupInvitation

    group = services.get_group(request.user, group_id)
    services._require_permission(request.user, group, GroupPermission.INVITE)
    form = InvitationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.create_invitation(request.user, group.pk, **form.cleaned_data)
        messages.success(request, "Іменне запрошення створено. Скопіюйте посилання та передайте адресату.")
        return redirect("students:invitations", group_id=group.pk)
    invitation_list = []
    for invite in GroupInvitation.objects.filter(group=group).order_by("-created_at"):
        invitation_list.append(
            {
                "invitation": invite,
                "url": request.build_absolute_uri(reverse("students:invitation", args=[invite.token])),
            }
        )
    return render(
        request,
        "students/invitations.html",
        {
            "group": group,
            "form": form,
            "invitation_list": invitation_list,
            "page_title": "Запрошення учасників",
            "nav": "invitations",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@_service_errors
def group_settings(request, group_id):
    group = services.get_group(request.user, group_id)
    services._require_permission(request.user, group, GroupPermission.EDIT_GROUP)
    form = GroupForm(request.POST if request.method == "POST" else None, initial={"name": group.name})
    if request.method == "POST" and form.is_valid():
        services.update_group(request.user, group.pk, **form.cleaned_data)
        messages.success(request, "Налаштування групи збережено.")
        return redirect("students:group_settings", group_id=group.pk)
    return render(
        request,
        "students/group_settings.html",
        {
            "group": group,
            "form": form,
            "nav": "settings",
            "page_title": "Налаштування групи",
        },
    )


@login_required
@require_GET
@_service_errors
def group_permissions(request, group_id):
    group = services.get_group(request.user, group_id)
    services._require_owner(request.user, group)
    return render(
        request,
        "students/group_permissions.html",
        {
            "group": group,
            "nav": "permissions",
            "page_title": "Ролі та дозволи",
            "policy_forms": [
                (policy, RolePolicyForm(instance=policy, auto_id=f"id_{policy.role}_%s"))
                for policy in group.role_policies.all()
            ],
        },
    )
