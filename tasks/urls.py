from django.urls import path

from . import views

app_name = "tasks"
urlpatterns = [
    path("tasks/", views.task_list, name="list"),
    path("tasks/table/", views.task_list, {"table": True}, name="table"),
    path("calendar/", views.calendar, name="calendar"),
    path("tasks/new/", views.task_editor, name="create"),
    path("tasks/<int:pk>/", views.task_detail, name="detail"),
    path("tasks/<int:pk>/edit/", views.task_editor, name="edit"),
    path("tasks/<int:pk>/status/", views.task_status, name="status"),
    path("tasks/<int:pk>/comments/", views.task_comment, name="comment"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="delete"),
    path("tasks/<int:pk>/attachments/<int:attachment_id>/", views.attachment, name="attachment"),
]
