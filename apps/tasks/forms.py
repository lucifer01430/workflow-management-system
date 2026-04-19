from django import forms

from apps.accounts.models import User, UserRole
from apps.departments.models import Department
from apps.tasks.models import (
    DeadlineExtensionRequest,
    ExtensionRequestStatus,
    Task,
    TaskCategory,
    TaskPriority,
    TaskProgressUpdate,
    TaskStatus,
    TaskType,
)


class TaskCreateForm(forms.ModelForm):
    assigned_to = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
        help_text="Select one or more employees for this task.",
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "category",
            "task_type",
            "priority",
            "department",
            "due_date",
            "estimated_hours",
            "approval_note",
            "internal_note",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "task_type": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "estimated_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "approval_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "internal_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = TaskCategory.objects.filter(is_active=True)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)

        self.fields["assigned_to"].queryset = self._get_assignable_users(user)

        if user and user.role == UserRole.HOD and user.department:
            self.fields["department"].initial = user.department
            self.fields["department"].disabled = True

    def _get_assignable_users(self, user):
        if not user:
            return User.objects.none()

        base_queryset = User.objects.filter(
            is_active=True,
            is_active_by_admin=True,
            registration_status="approved",
        )

        if user.role == UserRole.HOD and user.department:
            return base_queryset.filter(department=user.department, role=UserRole.EMPLOYEE)

        if user.role in [UserRole.GENERAL_MANAGER, UserRole.SUPER_ADMIN]:
            return base_queryset.filter(role__in=[UserRole.EMPLOYEE, UserRole.HOD])

        return User.objects.none()


class TaskStatusUpdateForm(forms.ModelForm):
    class Meta:
        model = TaskProgressUpdate
        fields = ["status", "note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (TaskStatus.NOT_STARTED, "Not Started"),
            (TaskStatus.IN_PROGRESS, "In Progress"),
            (TaskStatus.ON_HOLD, "On Hold"),
            (TaskStatus.COMPLETED, "Completed"),
        ]


class DeadlineExtensionRequestForm(forms.ModelForm):
    class Meta:
        model = DeadlineExtensionRequest
        fields = ["requested_due_date", "reason"]
        widgets = {
            "requested_due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class DeadlineExtensionReviewForm(forms.ModelForm):
    class Meta:
        model = DeadlineExtensionRequest
        fields = ["status", "review_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "review_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (ExtensionRequestStatus.APPROVED, "Approve"),
            (ExtensionRequestStatus.REJECTED, "Reject"),
        ]