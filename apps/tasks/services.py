from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.auditlogs.utils import log_activity
from apps.notifications.models import NotificationType
from apps.notifications.utils import create_notification, send_action_email
from apps.tasks.models import (
    DeadlineExtensionRequest,
    ExtensionRequestStatus,
    Task,
    TaskAssignment,
    TaskProgressUpdate,
    TaskStatus,
    TaskType,
)


@transaction.atomic
def create_task_with_workflow(*, form, created_by):
    task = form.save(commit=False)
    task.created_by = created_by

    if created_by.role == UserRole.HOD:
        task.department = created_by.department

    assigned_users = list(form.cleaned_data.get("assigned_to", []))

    if task.task_type == TaskType.QUICK:
        task.requires_gm_approval = False
        task.status = TaskStatus.ASSIGNED if assigned_users else TaskStatus.DRAFT
    else:
        task.requires_gm_approval = True
        task.status = TaskStatus.PENDING_APPROVAL

    task.save()

    if assigned_users:
        for index, user in enumerate(assigned_users):
            TaskAssignment.objects.create(
                task=task,
                assigned_to=user,
                assigned_by=created_by,
                is_primary=index == 0,
                is_active=True,
            )

    if task.task_type == TaskType.QUICK and assigned_users:
        for user in assigned_users:
            create_notification(
                recipient=user,
                title="New Task Assigned",
                message=f"You have been assigned a new task: {task.title}",
                notification_type=NotificationType.TASK_ASSIGNED,
                task=task,
            )

            send_action_email(
                subject="New Task Assigned",
                message=(
                    f"Hello {user.full_name},\n\n"
                    f"You have been assigned a new task.\n"
                    f"Task: {task.title}\n"
                    f"Priority: {task.get_priority_display()}\n"
                    f"Due Date: {task.due_date}\n\n"
                    f"Please check your dashboard for details."
                ),
                recipient_list=[user.email],
            )

        log_activity(
            actor=created_by,
            action="task_created_and_assigned",
            target_model="Task",
            target_id=task.id,
            description=f"Quick task '{task.title}' created and assigned.",
        )

    elif task.task_type == TaskType.APPROVAL:
        gm_users = User.objects.filter(
            role__in=[UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN],
            is_active=True,
            is_active_by_admin=True,
        )

        for gm in gm_users:
            create_notification(
                recipient=gm,
                title="Task Approval Required",
                message=f"A task is waiting for approval: {task.title}",
                notification_type=NotificationType.TASK_UPDATED,
                task=task,
            )

            send_action_email(
                subject="Task Approval Required",
                message=(
                    f"Hello {gm.full_name},\n\n"
                    f"A new task requires your approval.\n"
                    f"Task: {task.title}\n"
                    f"Created By: {created_by.full_name}\n"
                    f"Priority: {task.get_priority_display()}\n\n"
                    f"Please review it from the system dashboard."
                ),
                recipient_list=[gm.email],
            )

        log_activity(
            actor=created_by,
            action="task_created_for_approval",
            target_model="Task",
            target_id=task.id,
            description=f"Approval task '{task.title}' created and sent for approval.",
        )

    return task


@transaction.atomic
def approve_task(*, task, approved_by):
    if task.status != TaskStatus.PENDING_APPROVAL:
        return task

    task.status = TaskStatus.APPROVED
    task.approved_by = approved_by
    task.approved_at = timezone.now()
    task.save()

    assigned_users = task.assignments.filter(is_active=True).select_related("assigned_to")

    if assigned_users.exists():
        task.status = TaskStatus.ASSIGNED
        task.save()

        for assignment in assigned_users:
            user = assignment.assigned_to

            create_notification(
                recipient=user,
                title="Task Approved and Assigned",
                message=f"Your task has been approved: {task.title}",
                notification_type=NotificationType.TASK_APPROVED,
                task=task,
            )

            send_action_email(
                subject="Task Approved and Assigned",
                message=(
                    f"Hello {user.full_name},\n\n"
                    f"The following task has been approved and assigned to you:\n"
                    f"Task: {task.title}\n"
                    f"Priority: {task.get_priority_display()}\n"
                    f"Due Date: {task.due_date}\n\n"
                    f"Please check your dashboard for details."
                ),
                recipient_list=[user.email],
            )

    create_notification(
        recipient=task.created_by,
        title="Task Approved",
        message=f"Your task has been approved: {task.title}",
        notification_type=NotificationType.TASK_APPROVED,
        task=task,
    )

    send_action_email(
        subject="Task Approved",
        message=(
            f"Hello {task.created_by.full_name},\n\n"
            f"Your task has been approved.\n"
            f"Task: {task.title}\n\n"
            f"You can now track it from your dashboard."
        ),
        recipient_list=[task.created_by.email],
    )

    log_activity(
        actor=approved_by,
        action="task_approved",
        target_model="Task",
        target_id=task.id,
        description=f"Task '{task.title}' approved.",
    )

    return task


@transaction.atomic
def reject_task(*, task, rejected_by, reason=""):
    if task.status != TaskStatus.PENDING_APPROVAL:
        return task

    task.status = TaskStatus.REJECTED
    task.rejected_by = rejected_by
    task.rejected_at = timezone.now()
    task.rejection_reason = reason
    task.save()

    create_notification(
        recipient=task.created_by,
        title="Task Rejected",
        message=f"Your task has been rejected: {task.title}",
        notification_type=NotificationType.TASK_REJECTED,
        task=task,
    )

    send_action_email(
        subject="Task Rejected",
        message=(
            f"Hello {task.created_by.full_name},\n\n"
            f"Your task has been rejected.\n"
            f"Task: {task.title}\n"
            f"Reason: {reason or 'No reason provided'}\n\n"
            f"Please review and update accordingly."
        ),
        recipient_list=[task.created_by.email],
    )

    log_activity(
        actor=rejected_by,
        action="task_rejected",
        target_model="Task",
        target_id=task.id,
        description=f"Task '{task.title}' rejected. Reason: {reason or 'No reason provided'}",
    )

    return task


@transaction.atomic
def update_task_status(*, task, user, status, note=""):
    task.status = status

    if status == TaskStatus.COMPLETED:
        task.completed_at = timezone.now()

    task.save(update_fields=["status", "completed_at", "updated_at"])

    TaskProgressUpdate.objects.create(
        task=task,
        updated_by=user,
        status=status,
        note=note,
    )

    recipients = []

    if task.created_by and task.created_by != user:
        recipients.append(task.created_by)

    gm_users = User.objects.filter(
        role__in=[UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN],
        is_active=True,
        is_active_by_admin=True,
        registration_status="approved",
    ).exclude(id=user.id)

    for gm in gm_users:
        recipients.append(gm)

    unique_recipients = {r.id: r for r in recipients}.values()

    for recipient in unique_recipients:
        create_notification(
            recipient=recipient,
            title="Task Status Updated",
            message=f"Task '{task.title}' status changed to {task.get_status_display()}",
            notification_type=NotificationType.TASK_UPDATED,
            task=task,
        )

        send_action_email(
            subject="Task Status Updated",
            message=(
                f"Hello {recipient.full_name},\n\n"
                f"Task status has been updated.\n"
                f"Task: {task.title}\n"
                f"New Status: {task.get_status_display()}\n"
                f"Updated By: {user.full_name}\n\n"
                f"Please check the dashboard for details."
            ),
            recipient_list=[recipient.email],
        )

    log_activity(
        actor=user,
        action="task_status_updated",
        target_model="Task",
        target_id=task.id,
        description=f"Task '{task.title}' status updated to {task.get_status_display()}",
    )

    return task


@transaction.atomic
def create_deadline_extension_request(*, task, requested_by, requested_due_date, reason):
    request_obj = DeadlineExtensionRequest.objects.create(
        task=task,
        requested_by=requested_by,
        current_due_date=task.due_date,
        requested_due_date=requested_due_date,
        reason=reason,
    )

    recipients = []

    if task.created_by and task.created_by != requested_by:
        recipients.append(task.created_by)

    gm_users = User.objects.filter(
        role__in=[UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN],
        is_active=True,
        is_active_by_admin=True,
        registration_status="approved",
    ).exclude(id=requested_by.id)

    for gm in gm_users:
        recipients.append(gm)

    unique_recipients = {r.id: r for r in recipients}.values()

    for recipient in unique_recipients:
        create_notification(
            recipient=recipient,
            title="Deadline Extension Requested",
            message=f"Extension requested for task: {task.title}",
            notification_type=NotificationType.EXTENSION_REQUESTED,
            task=task,
        )

        send_action_email(
            subject="Deadline Extension Requested",
            message=(
                f"Hello {recipient.full_name},\n\n"
                f"A deadline extension has been requested.\n"
                f"Task: {task.title}\n"
                f"Current Due Date: {task.due_date}\n"
                f"Requested Due Date: {requested_due_date}\n"
                f"Requested By: {requested_by.full_name}\n"
                f"Reason: {reason}\n\n"
                f"Please review it from the dashboard."
            ),
            recipient_list=[recipient.email],
        )

    log_activity(
        actor=requested_by,
        action="deadline_extension_requested",
        target_model="Task",
        target_id=task.id,
        description=f"Deadline extension requested for task '{task.title}'",
    )

    return request_obj


@transaction.atomic
def review_deadline_extension_request(*, extension_request, reviewed_by, status, review_note=""):
    extension_request.status = status
    extension_request.reviewed_by = reviewed_by
    extension_request.reviewed_at = timezone.now()
    extension_request.review_note = review_note
    extension_request.save()

    task = extension_request.task

    if status == ExtensionRequestStatus.APPROVED:
        task.due_date = extension_request.requested_due_date
        task.save(update_fields=["due_date", "updated_at"])

    notification_type = (
        NotificationType.EXTENSION_APPROVED
        if status == ExtensionRequestStatus.APPROVED
        else NotificationType.EXTENSION_REJECTED
    )

    create_notification(
        recipient=extension_request.requested_by,
        title="Deadline Extension Reviewed",
        message=f"Your extension request for '{task.title}' was {status}.",
        notification_type=notification_type,
        task=task,
    )

    send_action_email(
        subject="Deadline Extension Reviewed",
        message=(
            f"Hello {extension_request.requested_by.full_name},\n\n"
            f"Your deadline extension request has been {status}.\n"
            f"Task: {task.title}\n"
            f"Requested Due Date: {extension_request.requested_due_date}\n"
            f"Review Note: {review_note or 'No note provided'}\n\n"
            f"Please check your dashboard for details."
        ),
        recipient_list=[extension_request.requested_by.email],
    )

    log_activity(
        actor=reviewed_by,
        action="deadline_extension_reviewed",
        target_model="DeadlineExtensionRequest",
        target_id=extension_request.id,
        description=f"Extension request for task '{task.title}' marked as {status}",
    )

    return extension_request