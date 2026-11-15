from django.urls import path

from . import views

app_name = "academics"
urlpatterns = [
    path("subjects/", views.subjects, name="subjects"),
    path("subjects/new/", views.subject_editor, name="subject_create"),
    path("subjects/<int:pk>/topics/", views.topic_create, name="topic_create"),
    path("subjects/<int:pk>/edit/", views.subject_editor, name="subject_edit"),
    path("groups/<int:group_id>/academic/", views.curriculum, name="curriculum"),
    path("semesters/", views.semesters, name="semesters"),
    path("semesters/new/", views.semester_editor, name="semester_create"),
    path("semesters/<int:pk>/edit/", views.semester_editor, name="semester_edit"),
    path("semesters/<int:pk>/activate/", views.activate, name="activate"),
]
