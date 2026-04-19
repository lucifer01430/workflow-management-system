from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import UserRole
from apps.tasks.forms import (
    DeadlineExtensionRequestForm,
    DeadlineExtensionReviewForm,
    TaskCreateForm,
    TaskStatusUpdateForm,
)
from apps.tasks.models import DeadlineExtensionRequest, Task, TaskStatus
from apps.tasks.services import (
    approve_task,
    create_deadline_extension_request,
    create_task_with_workflow,
    reject_task,
    review_deadline_extension_request,
    update_task_status,
)


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
        ).prefetch_related("assignments__assigned_to", "progress_updates__updated_by", "extension_requests__requested_by"),
        id=task_id,
    )

    user = request.user
    allowed = False
    can_manage = False
    is_assigned_employee = False

    if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        allowed = True
        can_manage = True
    elif user.role == UserRole.HOD and (task.created_by_id == user.id or task.department_id == user.department_id):
        allowed = True
        can_manage = True
    elif user.role == UserRole.EMPLOYEE and task.assignments.filter(assigned_to=user, is_active=True).exists():
        allowed = True
        is_assigned_employee = True

    if not allowed:
        messages.error(request, "You do not have permission to view this task.")
        return redirect("dashboard:home")

    context = {
        "task": task,
        "assignments": task.assignments.filter(is_active=True).select_related("assigned_to", "assigned_by"),
        "progress_updates": task.progress_updates.all(),
        "extension_requests": task.extension_requests.all(),
        "status_form": TaskStatusUpdateForm(),
        "extension_form": DeadlineExtensionRequestForm(),
        "can_manage": can_manage,
        "is_assigned_employee": is_assigned_employee,
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


@login_required
def update_task_status_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if not task.assignments.filter(assigned_to=request.user, is_active=True).exists():
        messages.error(request, "You do not have permission to update this task.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = TaskStatusUpdateForm(request.POST)
        if form.is_valid():
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

    if not task.assignments.filter(assigned_to=request.user, is_active=True).exists():
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
    extension_request = get_object_or_404(DeadlineExtensionRequest, id=request_id)

    if request.user.role not in [UserRole.HOD, UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
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