import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.departments.models import Department
from apps.tasks.models import Task, TaskPriority, TaskStatus


def _visible_tasks_for_user(user):
    queryset = Task.objects.select_related("department", "category", "created_by").prefetch_related(
        "assignments__assigned_to"
    )

    if user.role == UserRole.EMPLOYEE:
        return queryset.filter(assignments__assigned_to=user, assignments__is_active=True).distinct()
    if user.role == UserRole.HOD:
        return queryset.filter(Q(created_by=user) | Q(department=user.department)).distinct()
    if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return queryset.distinct()
    return Task.objects.none()


def _apply_filters(queryset, params):
    status = params.get("status")
    priority = params.get("priority")
    department_id = params.get("department")
    task_type = params.get("task_type")

    if status:
        queryset = queryset.filter(status=status)
    if priority:
        queryset = queryset.filter(priority=priority)
    if department_id:
        queryset = queryset.filter(department_id=department_id)
    if task_type:
        queryset = queryset.filter(task_type=task_type)

    return queryset


@login_required
def report_overview_view(request):
    task_queryset = _apply_filters(_visible_tasks_for_user(request.user), request.GET)

    context = {
        "tasks": task_queryset.order_by("-updated_at"),
        "status_choices": TaskStatus.choices,
        "priority_choices": TaskPriority.choices,
        "task_type_choices": Task._meta.get_field("task_type").choices,
        "departments": Department.objects.filter(is_active=True).order_by("name"),
        "filters": {
            "status": request.GET.get("status", ""),
            "priority": request.GET.get("priority", ""),
            "department": request.GET.get("department", ""),
            "task_type": request.GET.get("task_type", ""),
        },
        "summary": {
            "total": task_queryset.count(),
            "active": task_queryset.filter(
                status__in=[
                    TaskStatus.PENDING_APPROVAL,
                    TaskStatus.ASSIGNED,
                    TaskStatus.NOT_STARTED,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.ON_HOLD,
                ]
            ).count(),
            "completed": task_queryset.filter(
                status__in=[TaskStatus.COMPLETED, TaskStatus.CLOSED]
            ).count(),
            "overdue": task_queryset.filter(
                due_date__isnull=False,
                due_date__lt=timezone.now(),
            ).exclude(status__in=[TaskStatus.COMPLETED, TaskStatus.CLOSED, TaskStatus.CANCELLED]).count(),
        },
        "query_string": request.GET.urlencode(),
    }
    return render(request, "reports/overview.html", context)


@login_required
def report_export_csv_view(request):
    task_queryset = _apply_filters(_visible_tasks_for_user(request.user), request.GET).order_by("-updated_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="task-report.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Task ID",
            "Title",
            "Type",
            "Department",
            "Created By",
            "Priority",
            "Status",
            "Due Date",
            "Assigned Users",
            "Updated At",
        ]
    )

    for task in task_queryset:
        assigned_users = ", ".join(
            assignment.assigned_to.full_name or assignment.assigned_to.username
            for assignment in task.assignments.filter(is_active=True).select_related("assigned_to")
        )
        writer.writerow(
            [
                task.id,
                task.title,
                task.get_task_type_display(),
                task.department or "-",
                task.created_by.full_name or task.created_by.username,
                task.get_priority_display(),
                task.get_status_display(),
                task.due_date.strftime("%Y-%m-%d %H:%M") if task.due_date else "",
                assigned_users,
                task.updated_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    return response
