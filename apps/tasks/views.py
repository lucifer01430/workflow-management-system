from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.models import UserRole
from apps.tasks.forms import TaskCreateForm
from apps.tasks.services import create_task_with_workflow


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

            return redirect("dashboard:home")
    else:
        form = TaskCreateForm(user=request.user)

    return render(request, "tasks/create_task.html", {"form": form})