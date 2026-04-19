from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.auditlogs.utils import log_activity
from apps.notifications.models import NotificationType
from apps.notifications.utils import (
    create_notification,
    get_recipient_name,
    send_action_email,
    send_task_action_email,
)
from apps.tasks.models import (
    DeadlineExtensionRequest,
    ExtensionRequestStatus,
    Task,
    TaskAssignment,
    TaskProgressUpdate,
    TaskStatus,
    TaskType,
)


def _format_datetime(value):
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p")


def _approved_users_by_roles(*roles):
    return list(
        User.objects.filter(
            role__in=roles,
            is_active=True,
            is_active_by_admin=True,
            registration_status="approved",
        )
    )


def _active_assignments(task):
    return list(task.assignments.filter(is_active=True).select_related("assigned_to", "assigned_by"))


def _active_assignees(task):
    return [assignment.assigned_to for assignment in _active_assignments(task)]


def _department_hod(task):
    department = getattr(task, "department", None)
    hod = getattr(department, "hod", None)
    if not hod:
        return None
    if not getattr(hod, "is_active", False):
        return None
    if not getattr(hod, "is_active_by_admin", False):
        return None
    if getattr(hod, "registration_status", "") != "approved":
        return None
    return hod


def _unique_users(users, exclude_ids=None):
    exclude_ids = {value for value in (exclude_ids or set()) if value}
    unique = {}
    for user in users:
        if not user or not getattr(user, "id", None) or user.id in exclude_ids:
            continue
        unique[user.id] = user
    return list(unique.values())


def _task_watchers(
    task,
    *,
    actor=None,
    include_creator=True,
    include_assignees=True,
    include_department_hod=True,
    include_managers=False,
):
    users = []
    if include_creator and getattr(task, "created_by", None):
        users.append(task.created_by)
    if include_assignees:
        users.extend(_active_assignees(task))
    if include_department_hod:
        hod = _department_hod(task)
        if hod:
            users.append(hod)
    if include_managers:
        users.extend(_approved_users_by_roles(UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN))
    return _unique_users(users, exclude_ids={getattr(actor, "id", None)})


def _task_email_rows(task, extra_rows=None):
    rows = [
        {"label": "Task", "value": task.title},
        {"label": "Status", "value": task.get_status_display()},
        {"label": "Priority", "value": task.get_priority_display()},
        {"label": "Due Date", "value": _format_datetime(task.due_date)},
        {"label": "Department", "value": str(task.department) if task.department else "-"},
    ]
    if extra_rows:
        rows.extend(extra_rows)
    return rows


def _deliver_task_update(
    recipient,
    *,
    task,
    title,
    message,
    notification_type,
    email_subject=None,
    html_template=None,
    text_template=None,
    template_context=None,
    heading=None,
    intro=None,
    action_summary=None,
    detail_rows=None,
    footer_note="Please check your dashboard for the latest task details.",
):
    create_notification(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        task=task,
    )

    if not getattr(recipient, "email", None):
        return

    if html_template or text_template:
        context = dict(template_context or {})
        context.setdefault("subject", email_subject or title)
        context.setdefault("recipient_name", get_recipient_name(recipient))
        context.setdefault("heading", heading or title)
        context.setdefault("task", task)
        send_action_email(
            subject=email_subject or title,
            message=action_summary or message,
            recipient_list=[recipient.email],
            html_template=html_template,
            text_template=text_template,
            context=context,
        )
        return

    send_task_action_email(
        subject=email_subject or title,
        recipient=recipient,
        task=task,
        heading=heading or title,
        intro=intro or message,
        action_summary=action_summary or message,
        detail_rows=detail_rows or _task_email_rows(task),
        footer_note=footer_note,
    )


def _normalize_task_status_after_assignment_change(task):
    has_active_assignments = task.assignments.filter(is_active=True).exists()
    update_fields = []

    if task.task_type == TaskType.QUICK:
        if has_active_assignments and task.status == TaskStatus.DRAFT:
            task.status = TaskStatus.ASSIGNED
            update_fields.append("status")
        elif not has_active_assignments and task.status == TaskStatus.ASSIGNED:
            task.status = TaskStatus.DRAFT
            update_fields.append("status")
    elif task.task_type == TaskType.APPROVAL:
        if task.approved_at and has_active_assignments and task.status == TaskStatus.APPROVED:
            task.status = TaskStatus.ASSIGNED
            update_fields.append("status")
        elif task.approved_at and not has_active_assignments and task.status == TaskStatus.ASSIGNED:
            task.status = TaskStatus.APPROVED
            update_fields.append("status")

    if update_fields:
        task.save(update_fields=update_fields + ["updated_at"])


def _sync_task_assignments(*, task, assigned_users, assigned_by, notify_changes=False):
    desired_users = list(assigned_users)
    desired_ids = [user.id for user in desired_users]

    existing_assignments = {
        assignment.assigned_to_id: assignment
        for assignment in task.assignments.select_related("assigned_to").all()
    }
    active_assignments = {user_id: assignment for user_id, assignment in existing_assignments.items() if assignment.is_active}
    active_ids = set(active_assignments.keys())
    desired_id_set = set(desired_ids)

    added_users = []
    removed_users = []

    for user_id in active_ids - desired_id_set:
        assignment = active_assignments[user_id]
        assignment.is_active = False
        assignment.is_primary = False
        assignment.save(update_fields=["is_active", "is_primary"])
        removed_users.append(assignment.assigned_to)
        log_activity(
            actor=assigned_by,
            action="task_assignment_removed",
            target_model="Task",
            target_id=task.id,
            description=f"Assignment removed for '{assignment.assigned_to.full_name or assignment.assigned_to.username}' on task '{task.title}'.",
        )

    for index, user in enumerate(desired_users):
        if user.id in existing_assignments:
            assignment = existing_assignments[user.id]
            changed_fields = []
            if not assignment.is_active:
                assignment.is_active = True
                assignment.assigned_at = timezone.now()
                changed_fields.extend(["is_active", "assigned_at"])
                added_users.append(user)
            if assignment.assigned_by_id != assigned_by.id:
                assignment.assigned_by = assigned_by
                changed_fields.append("assigned_by")
            is_primary = index == 0
            if assignment.is_primary != is_primary:
                assignment.is_primary = is_primary
                changed_fields.append("is_primary")
            if changed_fields:
                assignment.save(update_fields=changed_fields)
        else:
            TaskAssignment.objects.create(
                task=task,
                assigned_to=user,
                assigned_by=assigned_by,
                is_primary=index == 0,
                is_active=True,
            )
            added_users.append(user)

        if user in added_users:
            log_activity(
                actor=assigned_by,
                action="task_assigned",
                target_model="Task",
                target_id=task.id,
                description=f"Task '{task.title}' assigned to '{user.full_name or user.username}'.",
            )

    _normalize_task_status_after_assignment_change(task)

    if not notify_changes:
        return {"added_users": added_users, "removed_users": removed_users}

    for user in added_users:
        _deliver_task_update(
            user,
            task=task,
            title="Task Assignment Updated",
            message=f"You have been assigned to task '{task.title}'.",
            notification_type=NotificationType.TASK_ASSIGNED,
            email_subject="Task Assignment Updated",
            heading="Task assignment updated",
            intro="You have been added as an assignee on a workflow task.",
            action_summary=f"{assigned_by.full_name or assigned_by.username} assigned you to '{task.title}'.",
            detail_rows=_task_email_rows(
                task,
                [{"label": "Assigned By", "value": assigned_by.full_name or assigned_by.username}],
            ),
        )

    for user in removed_users:
        _deliver_task_update(
            user,
            task=task,
            title="Task Assignment Updated",
            message=f"You have been removed from task '{task.title}'.",
            notification_type=NotificationType.TASK_UPDATED,
            email_subject="Task Assignment Updated",
            heading="Task assignment updated",
            intro="Your assignment on a workflow task has changed.",
            action_summary=f"{assigned_by.full_name or assigned_by.username} removed you from '{task.title}'.",
            detail_rows=_task_email_rows(
                task,
                [{"label": "Updated By", "value": assigned_by.full_name or assigned_by.username}],
            ),
        )

    if added_users or removed_users:
        change_bits = []
        if added_users:
            change_bits.append(
                "Added: " + ", ".join(user.full_name or user.username for user in added_users)
            )
        if removed_users:
            change_bits.append(
                "Removed: " + ", ".join(user.full_name or user.username for user in removed_users)
            )

        for recipient in _task_watchers(
            task,
            actor=assigned_by,
            include_creator=True,
            include_assignees=True,
            include_department_hod=True,
            include_managers=True,
        ):
            _deliver_task_update(
                recipient,
                task=task,
                title="Task Assignment Updated",
                message=f"Assignments were updated for task '{task.title}'.",
                notification_type=NotificationType.TASK_UPDATED,
                email_subject="Task Assignment Updated",
                heading="Task assignment updated",
                intro="Assignments changed on a workflow task you can access.",
                action_summary=" ".join(change_bits),
                detail_rows=_task_email_rows(
                    task,
                    [{"label": "Updated By", "value": assigned_by.full_name or assigned_by.username}],
                ),
            )

    return {"added_users": added_users, "removed_users": removed_users}


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
        _sync_task_assignments(task=task, assigned_users=assigned_users, assigned_by=created_by, notify_changes=False)

    if task.task_type == TaskType.QUICK:
        log_activity(
            actor=created_by,
            action="task_created",
            target_model="Task",
            target_id=task.id,
            description=f"Quick task '{task.title}' created.",
        )

        for user in assigned_users:
            _deliver_task_update(
                user,
                task=task,
                title="New Task Assigned",
                message=f"You have been assigned a new task: {task.title}",
                notification_type=NotificationType.TASK_ASSIGNED,
                email_subject="New Task Assigned",
                html_template="emails/task_assigned_email.html",
                text_template="emails/task_assigned_email.txt",
                template_context={
                    "subject": "New Task Assigned",
                    "heading": "New task assigned",
                    "recipient_name": get_recipient_name(user),
                    "task": task,
                    "action_copy": "Open your dashboard to review the task, timeline, and next required action.",
                },
                action_summary=f"{created_by.full_name or created_by.username} assigned '{task.title}' to you.",
            )

        if assigned_users:
            log_activity(
                actor=created_by,
                action="task_created_and_assigned",
                target_model="Task",
                target_id=task.id,
                description=f"Quick task '{task.title}' created and assigned.",
            )

    else:
        log_activity(
            actor=created_by,
            action="task_created_for_approval",
            target_model="Task",
            target_id=task.id,
            description=f"Approval task '{task.title}' created and sent for approval.",
        )

        for manager in _approved_users_by_roles(UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN):
            _deliver_task_update(
                manager,
                task=task,
                title="Task Approval Required",
                message=f"A task is waiting for approval: {task.title}",
                notification_type=NotificationType.TASK_UPDATED,
                email_subject="Task Approval Required",
                html_template="emails/task_approval_required_email.html",
                text_template="emails/task_approval_required_email.txt",
                template_context={
                    "subject": "Task Approval Required",
                    "heading": "Task approval required",
                    "recipient_name": get_recipient_name(manager),
                    "task": task,
                    "created_by_name": created_by.full_name or created_by.username,
                    "action_copy": "Review the task in the approval inbox and decide whether it should move forward.",
                },
                action_summary=f"{created_by.full_name or created_by.username} submitted '{task.title}' for approval.",
            )

    return task


@transaction.atomic
def update_task_details(*, task, form, updated_by):
    old_values = {
        "title": task.title,
        "description": task.description,
        "category_id": task.category_id,
        "task_type": task.task_type,
        "priority": task.priority,
        "department_id": task.department_id,
        "due_date": task.due_date,
        "estimated_hours": task.estimated_hours,
        "approval_note": task.approval_note,
        "internal_note": task.internal_note,
    }

    task = form.save(commit=False)
    if updated_by.role == UserRole.HOD:
        task.department = updated_by.department
    task.save()
    form.save_m2m()

    assignment_changes = _sync_task_assignments(
        task=task,
        assigned_users=list(form.cleaned_data.get("assigned_to", [])),
        assigned_by=updated_by,
        notify_changes=True,
    )

    if old_values["due_date"] != task.due_date:
        _notify_deadline_update(
            task=task,
            updated_by=updated_by,
            previous_due_date=old_values["due_date"],
            new_due_date=task.due_date,
        )

    if old_values["priority"] != task.priority:
        _notify_priority_update(
            task=task,
            updated_by=updated_by,
            previous_priority=old_values["priority"],
            new_priority=task.priority,
        )

    note_changes = []
    if old_values["approval_note"] != task.approval_note:
        note_changes.append("approval note")
    if old_values["internal_note"] != task.internal_note:
        note_changes.append("internal note")
    if note_changes:
        log_activity(
            actor=updated_by,
            action="task_notes_updated",
            target_model="Task",
            target_id=task.id,
            description=f"Updated {', '.join(note_changes)} on task '{task.title}'.",
        )

    generic_changed = []
    for key, label in [
        ("title", "title"),
        ("description", "description"),
        ("category_id", "category"),
        ("task_type", "task type"),
        ("department_id", "department"),
        ("estimated_hours", "estimated hours"),
    ]:
        if old_values[key] != getattr(task, key):
            generic_changed.append(label)

    if generic_changed:
        log_activity(
            actor=updated_by,
            action="task_details_updated",
            target_model="Task",
            target_id=task.id,
            description=f"Updated {', '.join(generic_changed)} on task '{task.title}'.",
        )

    if assignment_changes["added_users"] or assignment_changes["removed_users"]:
        log_activity(
            actor=updated_by,
            action="task_assignments_updated",
            target_model="Task",
            target_id=task.id,
            description=f"Assignments updated for task '{task.title}'.",
        )

    return task


@transaction.atomic
def approve_task(*, task, approved_by):
    if task.status != TaskStatus.PENDING_APPROVAL:
        return task

    task.status = TaskStatus.APPROVED
    task.approved_by = approved_by
    task.approved_at = timezone.now()
    task.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

    active_assignments = _active_assignments(task)
    if active_assignments:
        task.status = TaskStatus.ASSIGNED
        task.save(update_fields=["status", "updated_at"])

        for assignment in active_assignments:
            user = assignment.assigned_to
            _deliver_task_update(
                user,
                task=task,
                title="Task Approved and Assigned",
                message=f"Your task has been approved: {task.title}",
                notification_type=NotificationType.TASK_APPROVED,
                email_subject="Task Approved and Assigned",
                html_template="emails/task_approved_email.html",
                text_template="emails/task_approved_email.txt",
                template_context={
                    "subject": "Task Approved and Assigned",
                    "heading": "Task approved and assigned",
                    "recipient_name": get_recipient_name(user),
                    "task": task,
                    "actor_name": approved_by.full_name or approved_by.username,
                    "action_copy": "Open the dashboard to start work and review the task activity timeline.",
                },
                action_summary=f"{approved_by.full_name or approved_by.username} approved '{task.title}' and made it active for you.",
            )

            log_activity(
                actor=approved_by,
                action="task_assigned",
                target_model="Task",
                target_id=task.id,
                description=f"Approved task '{task.title}' assigned to '{user.full_name or user.username}'.",
            )

    creator = task.created_by
    assigned_user_ids = {assignment.assigned_to_id for assignment in active_assignments}
    if creator and creator.id not in assigned_user_ids:
        _deliver_task_update(
            creator,
            task=task,
            title="Task Approved",
            message=f"Your task has been approved: {task.title}",
            notification_type=NotificationType.TASK_APPROVED,
            email_subject="Task Approved",
            html_template="emails/task_approved_email.html",
            text_template="emails/task_approved_email.txt",
            template_context={
                "subject": "Task Approved",
                "heading": "Task approved",
                "recipient_name": get_recipient_name(creator),
                "task": task,
                "actor_name": approved_by.full_name or approved_by.username,
                "action_copy": "You can now monitor the task from the dashboard and detail view.",
            },
            action_summary=f"{approved_by.full_name or approved_by.username} approved '{task.title}'.",
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
    task.save(update_fields=["status", "rejected_by", "rejected_at", "rejection_reason", "updated_at"])

    recipients = _unique_users([task.created_by] + _active_assignees(task), exclude_ids={rejected_by.id})
    for recipient in recipients:
        _deliver_task_update(
            recipient,
            task=task,
            title="Task Rejected",
            message=f"Task '{task.title}' was rejected.",
            notification_type=NotificationType.TASK_REJECTED,
            email_subject="Task Rejected",
            html_template="emails/task_rejected_email.html",
            text_template="emails/task_rejected_email.txt",
            template_context={
                "subject": "Task Rejected",
                "heading": "Task rejected",
                "recipient_name": get_recipient_name(recipient),
                "task": task,
                "actor_name": rejected_by.full_name or rejected_by.username,
                "rejection_reason": reason or "No reason provided",
                "action_copy": "Review the rejection context in the workflow system before taking any next step.",
            },
            action_summary=f"{rejected_by.full_name or rejected_by.username} rejected '{task.title}'.",
        )

    log_activity(
        actor=rejected_by,
        action="task_rejected",
        target_model="Task",
        target_id=task.id,
        description=f"Task '{task.title}' rejected. Reason: {reason or 'No reason provided'}",
    )

    return task


def _notify_deadline_update(*, task, updated_by, previous_due_date, new_due_date):
    recipients = _task_watchers(
        task,
        actor=updated_by,
        include_creator=True,
        include_assignees=True,
        include_department_hod=True,
        include_managers=True,
    )
    for recipient in recipients:
        _deliver_task_update(
            recipient,
            task=task,
            title="Task Deadline Updated",
            message=f"Deadline updated for task '{task.title}'.",
            notification_type=NotificationType.DEADLINE_UPDATED,
            email_subject="Task Deadline Updated",
            heading="Task deadline updated",
            intro="A task deadline changed in the workflow system.",
            action_summary=f"{updated_by.full_name or updated_by.username} changed the deadline from {_format_datetime(previous_due_date)} to {_format_datetime(new_due_date)}.",
            detail_rows=_task_email_rows(
                task,
                [
                    {"label": "Previous Due Date", "value": _format_datetime(previous_due_date)},
                    {"label": "New Due Date", "value": _format_datetime(new_due_date)},
                    {"label": "Updated By", "value": updated_by.full_name or updated_by.username},
                ],
            ),
        )

    log_activity(
        actor=updated_by,
        action="task_deadline_updated",
        target_model="Task",
        target_id=task.id,
        description=f"Deadline updated for task '{task.title}' from {_format_datetime(previous_due_date)} to {_format_datetime(new_due_date)}.",
    )


@transaction.atomic
def update_task_deadline(*, task, updated_by, due_date):
    previous_due_date = task.due_date
    task.due_date = due_date
    task.save(update_fields=["due_date", "updated_at"])
    _notify_deadline_update(
        task=task,
        updated_by=updated_by,
        previous_due_date=previous_due_date,
        new_due_date=due_date,
    )
    return task


def _notify_priority_update(*, task, updated_by, previous_priority, new_priority):
    previous_label = dict(task._meta.get_field("priority").choices).get(previous_priority, previous_priority or "-")
    new_label = task.get_priority_display()

    recipients = _task_watchers(
        task,
        actor=updated_by,
        include_creator=True,
        include_assignees=True,
        include_department_hod=True,
        include_managers=True,
    )
    for recipient in recipients:
        _deliver_task_update(
            recipient,
            task=task,
            title="Task Priority Updated",
            message=f"Priority updated for task '{task.title}'.",
            notification_type=NotificationType.TASK_UPDATED,
            email_subject="Task Priority Updated",
            heading="Task priority updated",
            intro="A task priority changed in the workflow system.",
            action_summary=f"{updated_by.full_name or updated_by.username} changed the priority from {previous_label} to {new_label}.",
            detail_rows=_task_email_rows(
                task,
                [
                    {"label": "Previous Priority", "value": previous_label},
                    {"label": "New Priority", "value": new_label},
                    {"label": "Updated By", "value": updated_by.full_name or updated_by.username},
                ],
            ),
        )

    log_activity(
        actor=updated_by,
        action="task_priority_updated",
        target_model="Task",
        target_id=task.id,
        description=f"Priority updated for task '{task.title}' from {previous_label} to {new_label}.",
    )


@transaction.atomic
def update_task_priority(*, task, updated_by, priority):
    previous_priority = task.priority
    task.priority = priority
    task.save(update_fields=["priority", "updated_at"])
    _notify_priority_update(
        task=task,
        updated_by=updated_by,
        previous_priority=previous_priority,
        new_priority=priority,
    )
    return task


@transaction.atomic
def update_task_status(*, task, user, status, note=""):
    task.status = status
    update_fields = ["status", "updated_at"]

    if status == TaskStatus.COMPLETED and not task.completed_at:
        task.completed_at = timezone.now()
        update_fields.append("completed_at")

    if status == TaskStatus.CLOSED and not task.closed_at:
        task.closed_at = timezone.now()
        update_fields.append("closed_at")

    task.save(update_fields=update_fields)

    TaskProgressUpdate.objects.create(
        task=task,
        updated_by=user,
        status=status,
        note=note,
    )

    notification_type = (
        NotificationType.TASK_COMPLETED if status in [TaskStatus.COMPLETED, TaskStatus.CLOSED] else NotificationType.TASK_UPDATED
    )
    title = "Task Completed" if status in [TaskStatus.COMPLETED, TaskStatus.CLOSED] else "Task Status Updated"
    email_subject = title

    for recipient in _task_watchers(
        task,
        actor=user,
        include_creator=True,
        include_assignees=True,
        include_department_hod=True,
        include_managers=True,
    ):
        _deliver_task_update(
            recipient,
            task=task,
            title=title,
            message=f"Task '{task.title}' status changed to {task.get_status_display()}",
            notification_type=notification_type,
            email_subject=email_subject,
            heading="Task status updated",
            intro="A workflow task status changed.",
            action_summary=f"{user.full_name or user.username} updated the task to {task.get_status_display()}.",
            detail_rows=_task_email_rows(
                task,
                [
                    {"label": "Updated By", "value": user.full_name or user.username},
                    {"label": "New Status", "value": task.get_status_display()},
                    {"label": "Note", "value": note or "-"},
                ],
            ),
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

    recipients = _task_watchers(
        task,
        actor=requested_by,
        include_creator=True,
        include_assignees=False,
        include_department_hod=True,
        include_managers=True,
    )
    for recipient in recipients:
        _deliver_task_update(
            recipient,
            task=task,
            title="Deadline Extension Requested",
            message=f"Extension requested for task '{task.title}'.",
            notification_type=NotificationType.EXTENSION_REQUESTED,
            email_subject="Deadline Extension Requested",
            heading="Deadline extension requested",
            intro="A task deadline extension request needs visibility or review.",
            action_summary=f"{requested_by.full_name or requested_by.username} requested a new due date of {_format_datetime(requested_due_date)}.",
            detail_rows=_task_email_rows(
                task,
                [
                    {"label": "Requested By", "value": requested_by.full_name or requested_by.username},
                    {"label": "Current Due Date", "value": _format_datetime(task.due_date)},
                    {"label": "Requested Due Date", "value": _format_datetime(requested_due_date)},
                    {"label": "Reason", "value": reason},
                ],
            ),
        )

    log_activity(
        actor=requested_by,
        action="deadline_extension_requested",
        target_model="Task",
        target_id=task.id,
        description=f"Deadline extension requested for task '{task.title}'",
    )
    log_activity(
        actor=requested_by,
        action="deadline_extension_requested",
        target_model="DeadlineExtensionRequest",
        target_id=request_obj.id,
        description=f"Deadline extension request created for task '{task.title}'.",
    )

    return request_obj


@transaction.atomic
def review_deadline_extension_request(*, extension_request, reviewed_by, status, review_note=""):
    extension_request.status = status
    extension_request.reviewed_by = reviewed_by
    extension_request.reviewed_at = timezone.now()
    extension_request.review_note = review_note
    extension_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])

    task = extension_request.task
    if status == ExtensionRequestStatus.APPROVED:
        task.due_date = extension_request.requested_due_date
        task.save(update_fields=["due_date", "updated_at"])

    notification_type = (
        NotificationType.EXTENSION_APPROVED
        if status == ExtensionRequestStatus.APPROVED
        else NotificationType.EXTENSION_REJECTED
    )
    heading = "Deadline extension approved" if status == ExtensionRequestStatus.APPROVED else "Deadline extension rejected"
    subject = "Deadline Extension Approved" if status == ExtensionRequestStatus.APPROVED else "Deadline Extension Rejected"

    recipients = _task_watchers(
        task,
        actor=reviewed_by,
        include_creator=True,
        include_assignees=True,
        include_department_hod=True,
        include_managers=True,
    )
    recipients = _unique_users(recipients + [extension_request.requested_by], exclude_ids={reviewed_by.id})

    for recipient in recipients:
        _deliver_task_update(
            recipient,
            task=task,
            title="Deadline Extension Reviewed",
            message=f"Extension request for '{task.title}' was {status}.",
            notification_type=notification_type,
            email_subject=subject,
            heading=heading,
            intro="A deadline extension request has been reviewed.",
            action_summary=f"{reviewed_by.full_name or reviewed_by.username} {status} the extension request for '{task.title}'.",
            detail_rows=_task_email_rows(
                task,
                [
                    {"label": "Requested By", "value": extension_request.requested_by.full_name or extension_request.requested_by.username},
                    {"label": "Requested Due Date", "value": _format_datetime(extension_request.requested_due_date)},
                    {"label": "Decision", "value": status.title()},
                    {"label": "Review Note", "value": review_note or "-"},
                ],
            ),
        )

    log_activity(
        actor=reviewed_by,
        action="deadline_extension_reviewed",
        target_model="DeadlineExtensionRequest",
        target_id=extension_request.id,
        description=f"Extension request for task '{task.title}' marked as {status}",
    )
    log_activity(
        actor=reviewed_by,
        action="deadline_extension_reviewed",
        target_model="Task",
        target_id=task.id,
        description=f"Extension request for task '{task.title}' marked as {status}.",
    )

    return extension_request
