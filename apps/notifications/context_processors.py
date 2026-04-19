from apps.notifications.models import Notification


def notification_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "recent_notifications": [],
            "unread_notifications": [],
            "unread_notifications_count": 0,
        }

    unread_notifications = list(
        Notification.objects.filter(recipient=request.user, is_read=False)
        .select_related("task")
        .order_by("-created_at")[:5]
    )
    recent_notifications = list(
        Notification.objects.filter(recipient=request.user)
        .select_related("task")
        .order_by("-created_at")[:5]
    )

    return {
        "recent_notifications": recent_notifications,
        "unread_notifications": unread_notifications,
        "unread_notifications_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
    }
