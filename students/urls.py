from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("settings/account/email/", login_required(views.ProfileEmailView.as_view()), name="change_email"),
    path("settings/account/", views.account_settings, name="account_settings"),
    path("groups/", views.groups, name="groups"),
    path("groups/join/", views.join_group, name="join_group"),
    path("groups/<int:group_id>/invitations/manage/", views.invitations, name="invitations"),
    path("groups/new/", views.new_group, name="new_group"),
    path("groups/create/", views.create_group, name="create_group"),
    path("groups/<int:group_id>/", views.group_detail, name="group"),
    path("groups/<int:group_id>/settings/", views.group_settings, name="group_settings"),
    path("groups/<int:group_id>/permissions/", views.group_permissions, name="group_permissions"),
    path("groups/<int:group_id>/edit/", views.update_group, name="update_group"),
    path("groups/<int:group_id>/invitations/", views.create_invitation, name="create_invitation"),
    path(
        "groups/<int:group_id>/invitations/<int:invitation_id>/revoke/",
        views.revoke_invitation,
        name="revoke_invitation",
    ),
    path("invitations/<uuid:token>/", views.invitation, name="invitation"),
    path(
        "groups/<int:group_id>/requests/<int:request_id>/<str:decision>/", views.review_request, name="review_request"
    ),
    path("groups/<int:group_id>/members/<int:member_id>/role/", views.member_role, name="member_role"),
    path("groups/<int:group_id>/members/<int:member_id>/remove/", views.remove_member, name="remove_member"),
    path("groups/<int:group_id>/leave/", views.leave_group, name="leave_group"),
    path("groups/<int:group_id>/permissions/<str:role>/", views.role_permissions, name="role_permissions"),
]
