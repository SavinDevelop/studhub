from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "kind", "group", "created_at", "read_at")
    list_filter = ("kind", "read_at")
    search_fields = ("title", "recipient__email")
    readonly_fields = ("created_at",)
