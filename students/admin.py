from django.contrib import admin

from .models import GroupInvitation, GroupMembership, GroupRolePolicy, JoinRequest, StudentProfile, StudyGroup


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "first_name", "last_name", "completed_at")
    search_fields = ("first_name", "last_name", "user__email")


class MembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0


class PolicyInline(admin.TabularInline):
    model = GroupRolePolicy
    extra = 0


@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    inlines = (MembershipInline, PolicyInline)


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "status", "reviewed_by")
    readonly_fields = ("group", "user", "invitation", "status", "created_at", "reviewed_at", "reviewed_by")

    def has_add_permission(self, request):
        return False


@admin.register(GroupInvitation)
class GroupInvitationAdmin(admin.ModelAdmin):
    list_display = ("group", "created_by", "expires_at", "revoked_at")
    readonly_fields = ("token", "created_at")
