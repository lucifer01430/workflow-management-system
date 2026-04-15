from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.auditlogs.utils import log_activity
from apps.notifications.models import NotificationType
from apps.notifications.utils import create_notification, send_action_email
from apps.tasks.models import TaskAssignment, TaskStatus, TaskType


def _email_context(recipient_name, task, **extra):
    context = {
        "recipient_name": recipient_name,
        "task": task,
        "software_name": "Workflow Management System",
    }
    context.update(extra)
    return context


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
                html_template="emails/task_assigned_email.html",
                text_template="emails/task_assigned_email.txt",
                context=_email_context(
                    user.full_name or user.username,
                    task,
                    heading="New Task Assigned",
                    action_copy="Please check your dashboard to review the task details and due date.",
                ),
            )

        log_activity(
            actor=created_by,
            action="task_created_and_assigned",
            target_model="Task",
            target_id=task.id,
            description=f"Quick task '{task.title}' created and assigned.",
        )

    elif task.task_type == TaskType.APPROVAL:
        from apps.accounts.models import User

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
                html_template="emails/task_approval_required_email.html",
                text_template="emails/task_approval_required_email.txt",
                context=_email_context(
                    gm.full_name or gm.username,
                    task,
                    heading="Task Approval Required",
                    action_copy="A new task is waiting in the approval inbox for your review.",
                    created_by_name=created_by.full_name or created_by.username,
                ),
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
                html_template="emails/task_approved_email.html",
                text_template="emails/task_approved_email.txt",
                context=_email_context(
                    user.full_name or user.username,
                    task,
                    heading="Task Approved and Assigned",
                    action_copy="The approved task is now live in your dashboard.",
                    actor_name=approved_by.full_name or approved_by.username,
                ),
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
        html_template="emails/task_approved_email.html",
        text_template="emails/task_approved_email.txt",
        context=_email_context(
            task.created_by.full_name or task.created_by.username,
            task,
            heading="Task Approved",
            action_copy="You can now track task execution from your dashboard.",
            actor_name=approved_by.full_name or approved_by.username,
        ),
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
        html_template="emails/task_rejected_email.html",
        text_template="emails/task_rejected_email.txt",
        context=_email_context(
            task.created_by.full_name or task.created_by.username,
            task,
            heading="Task Rejected",
            action_copy="Please review the rejection reason and update the task details if needed.",
            actor_name=rejected_by.full_name or rejected_by.username,
            rejection_reason=reason or "No reason provided",
        ),
    )

    log_activity(
        actor=rejected_by,
        action="task_rejected",
        target_model="Task",
        target_id=task.id,
        description=f"Task '{task.title}' rejected. Reason: {reason or 'No reason provided'}",
    )

    return task
