from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.notifications.models import Notification


@login_required
def notification_list_view(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")

    context = {
        "notifications": notifications,
        "page_title": "Notifications",
    }
    return render(request, "notifications/list.html", context)


@login_required
def mark_notification_read_view(request, notification_id):
    notification = Notification.objects.filter(
        id=notification_id,
        recipient=request.user,
    ).first()

    if notification:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return redirect("notifications:list")