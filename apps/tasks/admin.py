from django.contrib import admin

from apps.tasks.models import Task, TaskAssignment, TaskCategory


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


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "task_type",
        "priority",
        "status",
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