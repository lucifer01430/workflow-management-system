from django.conf import settings
from django.core.mail import send_mail

from apps.notifications.models import Notification, NotificationType


def create_notification(recipient, title, message, notification_type=NotificationType.GENERAL, task=None):
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        task=task,
    )


def send_action_email(subject, message, recipient_list):
    if not recipient_list:
        return False

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )
    return True