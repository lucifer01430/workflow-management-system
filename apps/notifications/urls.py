from django.urls import path

from apps.notifications.views import mark_notification_read_view, notification_list_view

app_name = "notifications"

urlpatterns = [
    path("", notification_list_view, name="list"),
    path("read/<int:notification_id>/", mark_notification_read_view, name="mark_read"),
]