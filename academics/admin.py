from django.contrib import admin

from .models import Semester, Subject, Topic


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "academic_year_start", "starts_on", "ends_on", "is_active")
    list_filter = ("is_active", "academic_year_start", "group")
    search_fields = ("name", "group__name")


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 0


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "semester", "teacher_name", "is_archived")
    list_filter = ("is_archived", "semester__group", "semester")
    search_fields = ("name", "teacher_name", "teacher_email")
    inlines = (TopicInline,)
