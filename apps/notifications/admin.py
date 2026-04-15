from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "title",
        "notification_type",
        "task",
        "is_read",
        "created_at",
    )
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("recipient__email", "recipient__full_name", "title", "message")
    ordering = ("-created_at",)
    autocomplete_fields = ("recipient", "task")