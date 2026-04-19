from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.notifications.models import Notification


@login_required
def notification_list_view(request):
    notifications = Notification.objects.filter(recipient=request.user)
    search_query = request.GET.get("q", "").strip()

    if search_query:
        notifications = notifications.filter(
            Q(title__icontains=search_query) | Q(message__icontains=search_query)
        )

    notifications = notifications.order_by("-created_at")

    context = {
        "notifications": notifications,
        "page_title": "Notifications",
        "filters": {"q": search_query},
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

    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("notifications:list")
