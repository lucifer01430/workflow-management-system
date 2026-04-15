from django.contrib import admin
from django.utils.html import format_html

from apps.tasks.models import Task, TaskAssignment, TaskCategory, TaskStatus
from apps.tasks.services import approve_task, reject_task


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


class TaskAssignmentInline(admin.TabularInline):
    model = TaskAssignment
    extra = 1
    autocomplete_fields = ("assigned_to", "assigned_by")


@admin.action(description="Approve selected pending tasks")
def approve_selected_tasks(modeladmin, request, queryset):
    for task in queryset.filter(status=TaskStatus.PENDING_APPROVAL):
        approve_task(task=task, approved_by=request.user)


@admin.action(description="Reject selected pending tasks")
def reject_selected_tasks(modeladmin, request, queryset):
    for task in queryset.filter(status=TaskStatus.PENDING_APPROVAL):
        reject_task(task=task, rejected_by=request.user, reason="Rejected from admin action")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "task_type",
        "priority_badge",
        "status_badge",
        "department",
        "created_by",
        "requires_gm_approval",
        "approved_by",
        "due_date",
        "created_at",
    )
    list_filter = (
        "task_type",
        "priority",
        "status",
        "requires_gm_approval",
        "is_active",
        "department",
        "category",
    )
    search_fields = ("title", "description", "created_by__email", "created_by__full_name")
    ordering = ("-created_at",)
    autocomplete_fields = ("created_by", "department", "category", "approved_by", "rejected_by")
    inlines = [TaskAssignmentInline]
    actions = [approve_selected_tasks, reject_selected_tasks]

    def priority_badge(self, obj):
        colors = {
            "low": "#6c757d",
            "medium": "#0d6efd",
            "high": "#fd7e14",
            "urgent": "#dc3545",
        }
        return format_html(
            '<span style="padding:4px 8px;border-radius:12px;background:{};color:white;">{}</span>',
            colors.get(obj.priority, "#6c757d"),
            obj.get_priority_display(),
        )

    priority_badge.short_description = "Priority"

    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "pending_approval": "#ffc107",
            "approved": "#198754",
            "rejected": "#dc3545",
            "assigned": "#0d6efd",
            "not_started": "#6c757d",
            "in_progress": "#0dcaf0",
            "on_hold": "#fd7e14",
            "completed": "#198754",
            "closed": "#212529",
            "cancelled": "#dc3545",
        }
        return format_html(
            '<span style="padding:4px 8px;border-radius:12px;background:{};color:white;">{}</span>',
            colors.get(obj.status, "#6c757d"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task",
        "assigned_to",
        "assigned_by",
        "is_primary",
        "is_active",
        "assigned_at",
    )
    list_filter = ("is_primary", "is_active", "assigned_at")
    search_fields = ("task__title", "assigned_to__email", "assigned_to__full_name")
    ordering = ("-assigned_at",)
    autocomplete_fields = ("task", "assigned_to", "assigned_by")