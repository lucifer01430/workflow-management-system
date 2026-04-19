from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.accounts.utils import get_reporting_contacts
from apps.accounts.models import User, UserRole
from apps.notifications.models import Notification
from apps.tasks.models import Task, TaskStatus


@login_required
def dashboard_home(request):
    user = request.user

    if user.role == UserRole.EMPLOYEE:
        task_queryset = Task.objects.filter(
            assignments__assigned_to=user,
            assignments__is_active=True,
        ).distinct()

    elif user.role == UserRole.HOD:
        task_queryset = Task.objects.filter(
            Q(created_by=user) | Q(department=user.department)
        ).distinct()

    else:
        task_queryset = Task.objects.all().distinct()

    recent_notifications = Notification.objects.filter(
        recipient=user
    ).order_by("-created_at")[:5]

    unread_notifications = Notification.objects.filter(
        recipient=user,
        is_read=False,
    ).order_by("-created_at")[:5]

    unread_notifications_count = Notification.objects.filter(
        recipient=user,
        is_read=False,
    ).count()

    reporting_hod, reporting_gm = get_reporting_contacts(user)

    in_progress_count = task_queryset.filter(status=TaskStatus.IN_PROGRESS).count()
    assigned_tasks_count = task_queryset.filter(status=TaskStatus.ASSIGNED).count()
    pending_approval_count = task_queryset.filter(status=TaskStatus.PENDING_APPROVAL).count()

    recent_decisions = Task.objects.filter(
        status__in=[TaskStatus.APPROVED, TaskStatus.REJECTED]
    ).select_related("department", "created_by").order_by("-updated_at")[:5]

    total_users = User.objects.filter(
        is_active=True,
        is_active_by_admin=True,
        registration_status="approved",
    ).count()

    total_departments = 0
    rejected_count = Task.objects.filter(status=TaskStatus.REJECTED).count()

    if user.role == UserRole.SUPER_ADMIN:
        from apps.departments.models import Department
        total_departments = Department.objects.filter(is_active=True).count()

    context = {
        "total_tasks": task_queryset.count(),
        "pending_tasks": task_queryset.filter(
            status__in=[
                TaskStatus.PENDING_APPROVAL,
                TaskStatus.NOT_STARTED,
                TaskStatus.IN_PROGRESS,
                TaskStatus.ASSIGNED,
            ]
        ).count(),
        "completed_tasks": task_queryset.filter(
            status__in=[TaskStatus.COMPLETED, TaskStatus.CLOSED]
        ).count(),
        "pending_approvals": Task.objects.filter(status=TaskStatus.PENDING_APPROVAL).count()
        if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]
        else 0,
        "recent_notifications": recent_notifications,
        "unread_notifications": unread_notifications,
        "unread_notifications_count": unread_notifications_count,
        "reporting_hod": reporting_hod,
        "reporting_gm": reporting_gm,
        "in_progress_count": in_progress_count,
        "assigned_tasks_count": assigned_tasks_count,
        "pending_approval_count": pending_approval_count,
        "recent_decisions": recent_decisions,
        "total_users": total_users,
        "total_departments": total_departments,
        "rejected_count": rejected_count,
    }

    return render(request, "dashboard/home.html", context)
