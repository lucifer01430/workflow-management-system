from django.conf import settings
from django.db import models


class TaskType(models.TextChoices):
    QUICK = "quick", "Quick Task"
    APPROVAL = "approval", "Approval Task"


class TaskPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class TaskStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ASSIGNED = "assigned", "Assigned"
    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    ON_HOLD = "on_hold", "On Hold"
    COMPLETED = "completed", "Completed"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class ExtensionRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class TaskCategory(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Task Category"
        verbose_name_plural = "Task Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="tasks",
    )
    task_type = models.CharField(
        max_length=20,
        choices=TaskType.choices,
        default=TaskType.APPROVAL,
    )
    priority = models.CharField(
        max_length=20,
        choices=TaskPriority.choices,
        default=TaskPriority.MEDIUM,
    )
    status = models.CharField(
        max_length=30,
        choices=TaskStatus.choices,
        default=TaskStatus.DRAFT,
    )
    department = models.ForeignKey(
        "departments.Department",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_tasks",
    )
    requires_gm_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    due_date = models.DateTimeField(blank=True, null=True)
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    approval_note = models.TextField(blank=True, null=True)
    internal_note = models.TextField(blank=True, null=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="approved_tasks",
    )
    approved_at = models.DateTimeField(blank=True, null=True)

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="rejected_tasks",
    )
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)

    completed_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_task_type_display()})"


class TaskAssignment(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assigned_task_records",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Task Assignment"
        verbose_name_plural = "Task Assignments"
        ordering = ["-assigned_at"]
        unique_together = ("task", "assigned_to")

    def __str__(self):
        return f"{self.task.title} -> {self.assigned_to.full_name or self.assigned_to.username}"


class TaskProgressUpdate(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="progress_updates",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_progress_updates",
    )
    status = models.CharField(max_length=30, choices=TaskStatus.choices)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task.title} - {self.get_status_display()}"


class DeadlineExtensionRequest(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="extension_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deadline_extension_requests",
    )
    current_due_date = models.DateTimeField(blank=True, null=True)
    requested_due_date = models.DateTimeField()
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ExtensionRequestStatus.choices,
        default=ExtensionRequestStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_extension_requests",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    review_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Extension Request - {self.task.title}"