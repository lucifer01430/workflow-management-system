from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import UserRole
from apps.auditlogs.models import AuditLog
from apps.tasks.forms import (
    DeadlineExtensionRequestForm,
    DeadlineExtensionReviewForm,
    TaskCreateForm,
    TaskDeadlineUpdateForm,
    TaskPriorityUpdateForm,
    TaskRejectionForm,
    TaskStatusUpdateForm,
)
from apps.tasks.models import DeadlineExtensionRequest, Task, TaskStatus
from apps.tasks.services import (
    approve_task,
    create_deadline_extension_request,
    create_task_with_workflow,
    reject_task,
    review_deadline_extension_request,
    update_task_deadline,
    update_task_details,
    update_task_priority,
    update_task_status,
)


def _can_manage_task(user, task):
    if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return True
    if user.role == UserRole.HOD and (task.created_by_id == user.id or task.department_id == user.department_id):
        return True
    return False


def _is_assigned_employee(user, task):
    return user.role == UserRole.EMPLOYEE and task.assignments.filter(assigned_to=user, is_active=True).exists()


def _can_view_task(user, task):
    return _can_manage_task(user, task) or _is_assigned_employee(user, task)


def _activity_presentation(action):
    mapping = {
        "task_created": {"title": "Task created", "icon": "fa-plus", "accent": "primary"},
        "task_created_and_assigned": {"title": "Task created and assigned", "icon": "fa-user-plus", "accent": "info"},
        "task_created_for_approval": {"title": "Approval task created", "icon": "fa-paper-plane", "accent": "warning"},
        "task_approved": {"title": "Task approved", "icon": "fa-circle-check", "accent": "success"},
        "task_rejected": {"title": "Task rejected", "icon": "fa-circle-xmark", "accent": "danger"},
        "task_assigned": {"title": "Task assigned", "icon": "fa-user-plus", "accent": "info"},
        "task_assignment_removed": {"title": "Assignment removed", "icon": "fa-user-minus", "accent": "warning"},
        "task_assignments_updated": {"title": "Assignments updated", "icon": "fa-users-gear", "accent": "info"},
        "task_status_updated": {"title": "Status updated", "icon": "fa-arrows-rotate", "accent": "primary"},
        "task_deadline_updated": {"title": "Deadline updated", "icon": "fa-calendar-day", "accent": "warning"},
        "task_priority_updated": {"title": "Priority updated", "icon": "fa-flag", "accent": "danger"},
        "task_notes_updated": {"title": "Notes updated", "icon": "fa-note-sticky", "accent": "secondary"},
        "task_details_updated": {"title": "Task details updated", "icon": "fa-pen", "accent": "secondary"},
        "deadline_extension_requested": {"title": "Extension requested", "icon": "fa-hourglass-half", "accent": "warning"},
        "deadline_extension_reviewed": {"title": "Extension reviewed", "icon": "fa-clipboard-check", "accent": "success"},
    }
    return mapping.get(
        action,
        {
            "title": action.replace("_", " ").title(),
            "icon": "fa-clock-rotate-left",
            "accent": "secondary",
        },
    )


def _build_activity_timeline(task):
    extension_ids = list(task.extension_requests.values_list("id", flat=True))
    query = Q(target_model="Task", target_id=task.id)
    if extension_ids:
        query |= Q(target_model="DeadlineExtensionRequest", target_id__in=extension_ids)

    audit_entries = (
        AuditLog.objects.filter(query)
        .select_related("actor")
        .order_by("-created_at")
    )

    items = []
    for entry in audit_entries:
        presentation = _activity_presentation(entry.action)
        actor = entry.actor.full_name or entry.actor.username if entry.actor else "System"
        items.append(
            {
                "timestamp": entry.created_at,
                "title": presentation["title"],
                "icon": presentation["icon"],
                "accent": presentation["accent"],
                "actor": actor,
                "description": entry.description,
            }
        )
    return items


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

            return redirect("tasks:detail", task_id=task.id)
    else:
        form = TaskCreateForm(user=request.user)

    return render(request, "tasks/create_task.html", {"form": form})


@login_required
def edit_task_view(request, task_id):
    task = get_object_or_404(Task.objects.select_related("department", "created_by"), id=task_id)
    if not _can_manage_task(request.user, task):
        messages.error(request, "You do not have permission to edit this task.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = TaskCreateForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            update_task_details(task=task, form=form, updated_by=request.user)
            messages.success(request, "Task details updated successfully.")
            return redirect("tasks:detail", task_id=task.id)
    else:
        form = TaskCreateForm(instance=task, user=request.user)

    return render(request, "tasks/edit_task.html", {"form": form, "task": task})


@login_required
def my_tasks_view(request):
    user = request.user

    if user.role == UserRole.EMPLOYEE:
        tasks = (
            Task.objects.filter(assignments__assigned_to=user, assignments__is_active=True)
            .distinct()
            .select_related("department", "category", "created_by")
        )
    elif user.role == UserRole.HOD:
        tasks = (
            Task.objects.filter(Q(created_by=user) | Q(department=user.department))
            .distinct()
            .select_related("department", "category", "created_by")
        )
    elif user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        tasks = Task.objects.all().select_related("department", "category", "created_by")
    else:
        tasks = Task.objects.none()

    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    task_type_filter = request.GET.get("task_type", "").strip()

    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(created_by__full_name__icontains=search_query)
            | Q(created_by__username__icontains=search_query)
            | Q(department__name__icontains=search_query)
        )
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if task_type_filter:
        tasks = tasks.filter(task_type=task_type_filter)

    context = {
        "tasks": tasks.order_by("-updated_at"),
        "page_title": "My Tasks",
        "filters": {
            "q": search_query,
            "status": status_filter,
            "task_type": task_type_filter,
        },
        "status_choices": TaskStatus.choices,
        "task_type_choices": Task._meta.get_field("task_type").choices,
    }
    return render(request, "tasks/my_tasks.html", context)


@login_required
def task_detail_view(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related(
            "department",
            "department__hod",
            "category",
            "created_by",
            "approved_by",
            "rejected_by",
        ).prefetch_related(
            "assignments__assigned_to",
            "assignments__assigned_by",
            "progress_updates__updated_by",
            "extension_requests__requested_by",
            "extension_requests__reviewed_by",
        ),
        id=task_id,
    )

    if not _can_view_task(request.user, task):
        messages.error(request, "You do not have permission to view this task.")
        return redirect("dashboard:home")

    can_manage = _can_manage_task(request.user, task)
    is_assigned_employee = _is_assigned_employee(request.user, task)

    context = {
        "task": task,
        "assignments": task.assignments.filter(is_active=True).select_related("assigned_to", "assigned_by"),
        "progress_updates": task.progress_updates.select_related("updated_by").all(),
        "extension_requests": task.extension_requests.select_related("requested_by", "reviewed_by").all(),
        "activity_timeline": _build_activity_timeline(task),
        "employee_status_form": TaskStatusUpdateForm(),
        "manager_status_form": TaskStatusUpdateForm(manager=True),
        "deadline_form": TaskDeadlineUpdateForm(instance=task),
        "priority_form": TaskPriorityUpdateForm(instance=task),
        "extension_form": DeadlineExtensionRequestForm(),
        "rejection_form": TaskRejectionForm(initial={"reason": task.rejection_reason}),
        "can_manage": can_manage,
        "is_assigned_employee": is_assigned_employee,
        "can_approve_task": request.user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]
        and task.status == TaskStatus.PENDING_APPROVAL,
    }
    return render(request, "tasks/task_detail.html", context)


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
    search_query = request.GET.get("q", "").strip()
    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(created_by__full_name__icontains=search_query)
            | Q(created_by__username__icontains=search_query)
            | Q(department__name__icontains=search_query)
        )

    context = {
        "tasks": tasks.order_by("-updated_at"),
        "page_title": "Approval Inbox",
        "filters": {"q": search_query},
    }
    return render(request, "tasks/approval_inbox.html", context)


@login_required
def approve_task_view(request, task_id):
    if request.user.role not in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to approve tasks.")
        return redirect("dashboard:home")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    task = get_object_or_404(Task, id=task_id)
    approve_task(task=task, approved_by=request.user)
    messages.success(request, f"Task '{task.title}' approved successfully.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("tasks:detail", task_id=task.id)


@login_required
def reject_task_view(request, task_id):
    if request.user.role not in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        messages.error(request, "You do not have permission to reject tasks.")
        return redirect("dashboard:home")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    task = get_object_or_404(Task, id=task_id)
    if task.status != TaskStatus.PENDING_APPROVAL:
        messages.error(request, "Only pending approval tasks can be rejected.")
        return redirect("tasks:detail", task_id=task.id)

    form = TaskRejectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reject_task(task=task, rejected_by=request.user, reason=form.cleaned_data["reason"])
        messages.warning(request, f"Task '{task.title}' rejected.")
    else:
        messages.error(request, "Please provide a valid rejection reason.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("tasks:detail", task_id=task.id)


@login_required
def update_task_deadline_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if not _can_manage_task(request.user, task):
        messages.error(request, "You do not have permission to update this deadline.")
        return redirect("dashboard:home")

    form = TaskDeadlineUpdateForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        update_task_deadline(task=task, updated_by=request.user, due_date=form.cleaned_data["due_date"])
        messages.success(request, "Task deadline updated successfully.")
    else:
        messages.error(request, "Please provide a valid due date.")
    return redirect("tasks:detail", task_id=task.id)


@login_required
def update_task_priority_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if not _can_manage_task(request.user, task):
        messages.error(request, "You do not have permission to update this priority.")
        return redirect("dashboard:home")

    form = TaskPriorityUpdateForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        update_task_priority(task=task, updated_by=request.user, priority=form.cleaned_data["priority"])
        messages.success(request, "Task priority updated successfully.")
    else:
        messages.error(request, "Please provide a valid priority.")
    return redirect("tasks:detail", task_id=task.id)


@login_required
def update_task_status_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    can_manage = _can_manage_task(request.user, task)
    is_assigned_employee = _is_assigned_employee(request.user, task)

    if not can_manage and not is_assigned_employee:
        messages.error(request, "You do not have permission to update this task.")
        return redirect("dashboard:home")

    if can_manage and task.status == TaskStatus.PENDING_APPROVAL:
        messages.error(request, "Approve or reject this task before changing its workflow status.")
        return redirect("tasks:detail", task_id=task.id)

    form = TaskStatusUpdateForm(request.POST or None, manager=can_manage)
    if request.method == "POST" and form.is_valid():
        update_task_status(
            task=task,
            user=request.user,
            status=form.cleaned_data["status"],
            note=form.cleaned_data["note"],
        )
        messages.success(request, "Task status updated successfully.")
    else:
        messages.error(request, "Please correct the errors in the status update form.")

    return redirect("tasks:detail", task_id=task.id)


@login_required
def request_deadline_extension_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not _is_assigned_employee(request.user, task):
        messages.error(request, "You do not have permission to request an extension for this task.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = DeadlineExtensionRequestForm(request.POST)
        if form.is_valid():
            create_deadline_extension_request(
                task=task,
                requested_by=request.user,
                requested_due_date=form.cleaned_data["requested_due_date"],
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "Deadline extension request submitted successfully.")
        else:
            messages.error(request, "Please correct the errors in the extension request form.")

    return redirect("tasks:detail", task_id=task.id)


@login_required
def review_extension_request_view(request, request_id):
    extension_request = get_object_or_404(
        DeadlineExtensionRequest.objects.select_related("task", "requested_by", "reviewed_by"),
        id=request_id,
    )

    if not _can_manage_task(request.user, extension_request.task):
        messages.error(request, "You do not have permission to review this request.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = DeadlineExtensionReviewForm(request.POST, instance=extension_request)
        if form.is_valid():
            review_deadline_extension_request(
                extension_request=extension_request,
                reviewed_by=request.user,
                status=form.cleaned_data["status"],
                review_note=form.cleaned_data["review_note"],
            )
            messages.success(request, "Extension request reviewed successfully.")
        else:
            messages.error(request, "Please correct the review form errors.")

    return redirect("tasks:detail", task_id=extension_request.task.id)
