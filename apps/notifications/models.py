from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    TASK_ASSIGNED = "task_assigned", "Task Assigned"
    TASK_APPROVED = "task_approved", "Task Approved"
    TASK_REJECTED = "task_rejected", "Task Rejected"
    TASK_UPDATED = "task_updated", "Task Updated"
    TASK_COMPLETED = "task_completed", "Task Completed"
    COMMENT_ADDED = "comment_added", "Comment Added"
    DEADLINE_UPDATED = "deadline_updated", "Deadline Updated"
    EXTENSION_REQUESTED = "extension_requested", "Extension Requested"
    EXTENSION_APPROVED = "extension_approved", "Extension Approved"
    EXTENSION_REJECTED = "extension_rejected", "Extension Rejected"
    ACCOUNT_APPROVED = "account_approved", "Account Approved"
    ACCOUNT_REJECTED = "account_rejected", "Account Rejected"
    GENERAL = "general", "General"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.email} - {self.title}"