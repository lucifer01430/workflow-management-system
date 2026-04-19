from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import get_template
from xhtml2pdf import pisa
from openpyxl import Workbook

from apps.accounts.models import User, UserRole
from apps.departments.models import Department
from apps.tasks.models import Task, TaskPriority, TaskStatus, TaskType


def _get_report_queryset(request):
    user = request.user
    queryset = Task.objects.select_related(
        "department",
        "category",
        "created_by",
        "approved_by",
        "rejected_by",
    ).prefetch_related("assignments__assigned_to")

    if user.role == UserRole.HOD:
        queryset = queryset.filter(
            Q(created_by=user) | Q(department=user.department)
        ).distinct()

    elif user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        queryset = queryset.distinct()
    else:
        return Task.objects.none()

    department_id = request.GET.get("department")
    employee_id = request.GET.get("employee")
    status = request.GET.get("status")
    priority = request.GET.get("priority")
    task_type = request.GET.get("task_type")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if department_id:
        queryset = queryset.filter(department_id=department_id)

    if employee_id:
        queryset = queryset.filter(assignments__assigned_to_id=employee_id).distinct()

    if status:
        queryset = queryset.filter(status=status)

    if priority:
        queryset = queryset.filter(priority=priority)

    if task_type:
        queryset = queryset.filter(task_type=task_type)

    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)

    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    return queryset.order_by("-created_at")


@login_required
def report_dashboard_view(request):
    if request.user.role not in [UserRole.HOD, UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return render(request, "reports/no_access.html", status=403)

    queryset = _get_report_queryset(request)

    departments = Department.objects.filter(is_active=True).order_by("name")

    if request.user.role == UserRole.HOD and request.user.department:
        employees = User.objects.filter(
            department=request.user.department,
            is_active=True,
            is_active_by_admin=True,
            registration_status="approved",
        ).order_by("full_name")
    else:
        employees = User.objects.filter(
            is_active=True,
            is_active_by_admin=True,
            registration_status="approved",
        ).order_by("full_name")

    context = {
        "tasks": queryset,
        "departments": departments,
        "employees": employees,
        "status_choices": TaskStatus.choices,
        "priority_choices": TaskPriority.choices,
        "task_type_choices": TaskType.choices,
        "total_tasks": queryset.count(),
        "completed_tasks": queryset.filter(status__in=[TaskStatus.COMPLETED, TaskStatus.CLOSED]).count(),
        "pending_tasks": queryset.filter(
            status__in=[TaskStatus.PENDING_APPROVAL, TaskStatus.ASSIGNED, TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS]
        ).count(),
        "overdue_tasks": queryset.filter(
            due_date__isnull=False
        ).exclude(
            status__in=[TaskStatus.COMPLETED, TaskStatus.CLOSED, TaskStatus.CANCELLED]
        ).count(),
    }
    return render(request, "reports/dashboard.html", context)


@login_required
def export_tasks_excel_view(request):
    if request.user.role not in [UserRole.HOD, UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return HttpResponse("Unauthorized", status=403)

    queryset = _get_report_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Task Report"

    headers = [
        "Task ID",
        "Title",
        "Department",
        "Category",
        "Task Type",
        "Priority",
        "Status",
        "Created By",
        "Due Date",
        "Created At",
    ]
    sheet.append(headers)

    for task in queryset:
        sheet.append([
            task.id,
            task.title,
            str(task.department) if task.department else "-",
            str(task.category) if task.category else "-",
            task.get_task_type_display(),
            task.get_priority_display(),
            task.get_status_display(),
            task.created_by.full_name or task.created_by.username,
            task.due_date.strftime("%d-%m-%Y %I:%M %p") if task.due_date else "-",
            task.created_at.strftime("%d-%m-%Y %I:%M %p"),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="task_report.xlsx"'
    workbook.save(response)
    return response


@login_required
def export_tasks_pdf_view(request):
    if request.user.role not in [UserRole.HOD, UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
        return HttpResponse("Unauthorized", status=403)

    queryset = _get_report_queryset(request)

    template = get_template("reports/task_report_pdf.html")
    html = template.render({
        "tasks": queryset,
        "generated_by": request.user,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="task_report.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response