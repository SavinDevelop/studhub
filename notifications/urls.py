from django.urls import path

from . import views

app_name = "notifications"
urlpatterns = [
    path("notifications/", views.inbox, name="inbox"),
    path("notifications/read/", views.read, name="read_all"),
    path("notifications/<int:pk>/read/", views.read, name="read"),
]
