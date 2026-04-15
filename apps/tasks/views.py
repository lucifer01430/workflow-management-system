from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import UserRole
from apps.auditlogs.utils import log_activity
from apps.notifications.models import NotificationType
from apps.notifications.utils import create_notification
from apps.tasks.forms import (
    TaskCreateForm,
    TaskDeadlineUpdateForm,
    TaskEditForm,
    TaskPriorityUpdateForm,
    TaskStatusUpdateForm,
)
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import approve_task, create_task_with_workflow, reject_task


def _user_can_view_task(user, task):
    if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return True
    if user.role == UserRole.HOD and (task.created_by_id == user.id or task.department_id == user.department_id):
        return True
    if user.role == UserRole.EMPLOYEE and task.assignments.filter(assigned_to=user, is_active=True).exists():
        return True
    return False


def _user_can_manage_task(user, task):
    if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return True
    if user.role == UserRole.HOD and (task.created_by_id == user.id or task.department_id == user.department_id):
        return True
    return False


def _managed_task_or_redirect(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related(
            "department",
            "category",
            "created_by",
            "approved_by",
            "rejected_by",
        ).prefetch_related("assignments__assigned_to"),
        id=task_id,
    )

    if not _user_can_manage_task(request.user, task):
        messages.error(request, "You do not have permission to update this task.")
        return None
    return task


@login_required
def create_task_view(request):
    if request.user.role not in [UserRole.HOD, UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to create tasks.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = TaskCreateForm(request.POST, user=request.user)
        if form.is_valid():
            task = create_task_with_workflow(form=form, created_by=request.user)

            if task.task_type == "quick":
                messages.success(request, "Quick task created successfully.")
            else:
                messages.success(request, "Task request created and sent for approval.")

            return redirect("tasks:my_tasks")
    else:
        form = TaskCreateForm(user=request.user)

    return render(request, "tasks/create_task.html", {"form": form})


@login_required
def my_tasks_view(request):
    user = request.user

    if user.role == UserRole.EMPLOYEE:
        tasks = Task.objects.filter(
            assignments__assigned_to=user,
            assignments__is_active=True,
        ).distinct().select_related("department", "category", "created_by")

    elif user.role == UserRole.HOD:
        tasks = Task.objects.filter(
            Q(created_by=user) | Q(department=user.department)
        ).distinct().select_related("department", "category", "created_by")

    elif user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        tasks = Task.objects.all().select_related("department", "category", "created_by")

    else:
        tasks = Task.objects.none()

    context = {
        "tasks": tasks,
        "page_title": "My Tasks",
    }
    return render(request, "tasks/my_tasks.html", context)


@login_required
def task_detail_view(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related(
            "department",
            "category",
            "created_by",
            "approved_by",
            "rejected_by",
        ).prefetch_related("assignments__assigned_to"),
        id=task_id,
    )

    if not _user_can_view_task(request.user, task):
        messages.error(request, "You do not have permission to view this task.")
        return redirect("dashboard:home")

    can_manage_task = _user_can_manage_task(request.user, task)
    context = {
        "task": task,
        "assignments": task.assignments.filter(is_active=True).select_related("assigned_to", "assigned_by"),
        "can_manage_task": can_manage_task,
        "deadline_form": TaskDeadlineUpdateForm(instance=task) if can_manage_task else None,
        "priority_form": TaskPriorityUpdateForm(instance=task) if can_manage_task else None,
        "status_form": TaskStatusUpdateForm(instance=task) if can_manage_task else None,
    }
    return render(request, "tasks/task_detail.html", context)


@login_required
def edit_task_view(request, task_id):
    task = _managed_task_or_redirect(request, task_id)
    if not task:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = TaskEditForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            updated_task = form.save()
            form.save_assignments(updated_task, request.user)

            create_notification(
                recipient=updated_task.created_by,
                title="Task Updated",
                message=f"Task details were updated: {updated_task.title}",
                notification_type=NotificationType.TASK_UPDATED,
                task=updated_task,
            )
            log_activity(
                actor=request.user,
                action="task_updated",
                target_model="Task",
                target_id=updated_task.id,
                description=f"Task '{updated_task.title}' was edited.",
            )
            messages.success(request, "Task details updated successfully.")
            return redirect("tasks:detail", task_id=updated_task.id)
    else:
        form = TaskEditForm(instance=task, user=request.user)

    return render(
        request,
        "tasks/edit_task.html",
        {
            "form": form,
            "task": task,
        },
    )


@login_required
def update_task_deadline_view(request, task_id):
    task = _managed_task_or_redirect(request, task_id)
    if not task:
        return redirect("dashboard:home")
    if request.method != "POST":
        return redirect("tasks:detail", task_id=task_id)

    form = TaskDeadlineUpdateForm(request.POST, instance=task)
    if form.is_valid():
        updated_task = form.save()
        create_notification(
            recipient=updated_task.created_by,
            title="Task Deadline Updated",
            message=f"Deadline updated for task: {updated_task.title}",
            notification_type=NotificationType.DEADLINE_UPDATED,
            task=updated_task,
        )
        log_activity(
            actor=request.user,
            action="task_deadline_updated",
            target_model="Task",
            target_id=updated_task.id,
            description=f"Deadline updated for task '{updated_task.title}'.",
        )
        messages.success(request, "Task deadline updated successfully.")
    else:
        messages.error(request, "Please provide a valid deadline.")
    return redirect("tasks:detail", task_id=task_id)


@login_required
def update_task_priority_view(request, task_id):
    task = _managed_task_or_redirect(request, task_id)
    if not task:
        return redirect("dashboard:home")
    if request.method != "POST":
        return redirect("tasks:detail", task_id=task_id)

    form = TaskPriorityUpdateForm(request.POST, instance=task)
    if form.is_valid():
        updated_task = form.save()
        log_activity(
            actor=request.user,
            action="task_priority_updated",
            target_model="Task",
            target_id=updated_task.id,
            description=f"Priority updated for task '{updated_task.title}'.",
        )
        messages.success(request, "Task priority updated successfully.")
    else:
        messages.error(request, "Please select a valid priority.")
    return redirect("tasks:detail", task_id=task_id)


@login_required
def update_task_status_view(request, task_id):
    task = _managed_task_or_redirect(request, task_id)
    if not task:
        return redirect("dashboard:home")
    if request.method != "POST":
        return redirect("tasks:detail", task_id=task_id)

    form = TaskStatusUpdateForm(request.POST, instance=task)
    if form.is_valid():
        updated_task = form.save()
        log_activity(
            actor=request.user,
            action="task_status_updated",
            target_model="Task",
            target_id=updated_task.id,
            description=f"Status updated for task '{updated_task.title}'.",
        )
        messages.success(request, "Task status updated successfully.")
    else:
        messages.error(request, "Please select a valid status.")
    return redirect("tasks:detail", task_id=task_id)


@login_required
def approval_inbox_view(request):
    if request.user.role not in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to access the approval inbox.")
        return redirect("dashboard:home")

    tasks = Task.objects.filter(status=TaskStatus.PENDING_APPROVAL).select_related(
        "department",
        "category",
        "created_by",
    )

    context = {
        "tasks": tasks,
        "page_title": "Approval Inbox",
    }
    return render(request, "tasks/approval_inbox.html", context)


@login_required
def approve_task_view(request, task_id):
    if request.user.role not in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to approve tasks.")
        return redirect("dashboard:home")

    task = get_object_or_404(Task, id=task_id)
    approve_task(task=task, approved_by=request.user)
    messages.success(request, f"Task '{task.title}' approved successfully.")
    return redirect("tasks:approval_inbox")


@login_required
def reject_task_view(request, task_id):
    if request.user.role not in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to reject tasks.")
        return redirect("dashboard:home")

    task = get_object_or_404(Task, id=task_id)
    reason = request.POST.get("reason", "").strip() if request.method == "POST" else ""
    reject_task(task=task, rejected_by=request.user, reason=reason or "Rejected from approval inbox")
    messages.warning(request, f"Task '{task.title}' rejected.")
    return redirect("tasks:approval_inbox")
