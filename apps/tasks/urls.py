from django.urls import path

from apps.tasks.views import create_task_view

app_name = "tasks"

urlpatterns = [
    path("create/", create_task_view, name="create"),
]