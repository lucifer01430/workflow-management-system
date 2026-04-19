from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.notifications.models import Notification, NotificationType


def create_notification(recipient, title, message, notification_type=NotificationType.GENERAL, task=None):
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        task=task,
    )


def send_action_email(
    subject,
    message,
    recipient_list,
    *,
    html_template=None,
    text_template=None,
    context=None,
):
    if not recipient_list:
        return False

    context = context or {}
    html_message = render_to_string(html_template, context) if html_template else None

    if text_template:
        text_message = render_to_string(text_template, context)
    elif html_message:
        text_message = strip_tags(html_message)
    else:
        text_message = message

    send_mail(
        subject=subject,
        message=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
        html_message=html_message,
    )
    return True


def get_recipient_name(user):
    return getattr(user, "full_name", None) or getattr(user, "username", None) or getattr(user, "email", "User")


def send_task_action_email(
    *,
    subject,
    recipient,
    task,
    heading,
    intro,
    action_summary,
    detail_rows=None,
    footer_note="Please check your dashboard for the latest task details.",
):
    detail_rows = detail_rows or []
    context = {
        "subject": subject,
        "recipient_name": get_recipient_name(recipient),
        "heading": heading,
        "intro": intro,
        "task": task,
        "action_summary": action_summary,
        "detail_rows": detail_rows,
        "footer_note": footer_note,
    }
    return send_action_email(
        subject=subject,
        message=action_summary,
        recipient_list=[recipient.email] if getattr(recipient, "email", None) else [],
        html_template="emails/task_action_update_email.html",
        text_template="emails/task_action_update_email.txt",
        context=context,
    )
