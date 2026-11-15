from django.contrib import admin

from .models import SubmissionLink, Task, TaskAttachment, TaskComment, TaskProgress


class SubmissionLinkInline(admin.TabularInline):
    model = SubmissionLink
    extra = 1


class AttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "topic", "deadline", "is_required", "priority", "work_type")
    list_filter = ("is_required", "subject__semester__group", "subject", "deadline", "priority", "work_type")
    search_fields = ("title", "topic__name", "subject__name", "description", "legacy_subject", "legacy_topic")
    inlines = (SubmissionLinkInline, AttachmentInline)


@admin.register(TaskProgress)
class TaskProgressAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "status", "updated_at")
    list_filter = ("status", "task__subject__semester__group")


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("body",)
