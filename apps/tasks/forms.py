from django import forms

from apps.accounts.models import UserRole
from apps.departments.models import Department
from apps.notifications.models import NotificationType
from apps.notifications.utils import create_notification, send_action_email
from apps.tasks.models import Task, TaskAssignment, TaskCategory, TaskPriority, TaskStatus


class AssignableUsersMixin:
    def _get_assignable_users(self, user):
        from apps.accounts.models import User

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

        return base_queryset.none()


class TaskCreateForm(AssignableUsersMixin, forms.ModelForm):
    assigned_to = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
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


class TaskEditForm(AssignableUsersMixin, forms.ModelForm):
    assigned_to = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        help_text="Update the active assignees for this task.",
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "category",
            "priority",
            "department",
            "due_date",
            "estimated_hours",
            "approval_note",
            "internal_note",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "estimated_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "approval_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "internal_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["category"].queryset = TaskCategory.objects.filter(is_active=True)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["assigned_to"].queryset = self._get_assignable_users(user)

        if self.instance.pk:
            self.fields["assigned_to"].initial = self.instance.assignments.filter(is_active=True).values_list(
                "assigned_to_id",
                flat=True,
            )

        if user and user.role == UserRole.HOD and user.department:
            self.fields["department"].initial = user.department
            self.fields["department"].disabled = True

    def save_assignments(self, task, acting_user):
        selected_users = list(self.cleaned_data.get("assigned_to", []))
        selected_ids = [user.id for user in selected_users]
        selected_lookup = {user.id: user for user in selected_users}
        current_assignments = {
            assignment.assigned_to_id: assignment
            for assignment in task.assignments.select_related("assigned_to").all()
        }

        for assignee_id, assignment in current_assignments.items():
            should_be_active = assignee_id in selected_ids
            updates = []

            if assignment.is_active != should_be_active:
                assignment.is_active = should_be_active
                updates.append("is_active")

            is_primary = bool(selected_ids and assignee_id == selected_ids[0] and should_be_active)
            if assignment.is_primary != is_primary:
                assignment.is_primary = is_primary
                updates.append("is_primary")

            if updates:
                assignment.save(update_fields=updates)

        new_assignees = [selected_lookup[user_id] for user_id in selected_ids if user_id not in current_assignments]

        for index, assignee in enumerate(new_assignees):
            assignment = TaskAssignment.objects.create(
                task=task,
                assigned_to=assignee,
                assigned_by=acting_user,
                is_primary=not current_assignments and index == 0,
                is_active=True,
            )
            current_assignments[assignment.assigned_to_id] = assignment

            create_notification(
                recipient=assignee,
                title="Task Assignment Updated",
                message=f"You have been assigned to the task: {task.title}",
                notification_type=NotificationType.TASK_ASSIGNED,
                task=task,
            )
            send_action_email(
                subject="Task Assignment Updated",
                message=(
                    f"Hello {assignee.full_name},\n\n"
                    f"You have been assigned to the task '{task.title}'.\n"
                    f"Priority: {task.get_priority_display()}\n"
                    f"Due Date: {task.due_date or '-'}\n"
                ),
                recipient_list=[assignee.email],
                html_template="emails/task_assigned_email.html",
                text_template="emails/task_assigned_email.txt",
                context={
                    "recipient_name": assignee.full_name or assignee.username,
                    "task": task,
                    "heading": "Task Assignment Updated",
                    "action_copy": "Please open your dashboard to review the updated assignment details.",
                },
            )

        active_assignments = list(task.assignments.filter(is_active=True).order_by("-is_primary", "-assigned_at"))
        if active_assignments and not any(assignment.is_primary for assignment in active_assignments):
            primary_assignment = active_assignments[0]
            primary_assignment.is_primary = True
            primary_assignment.save(update_fields=["is_primary"])


class TaskDeadlineUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["due_date"]
        widgets = {
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        }


class TaskPriorityUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["priority"]
        widgets = {
            "priority": forms.Select(attrs={"class": "form-select"}),
        }


class TaskStatusUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["status"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_statuses = [
            TaskStatus.DRAFT,
            TaskStatus.ASSIGNED,
            TaskStatus.NOT_STARTED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.ON_HOLD,
            TaskStatus.COMPLETED,
            TaskStatus.CLOSED,
            TaskStatus.CANCELLED,
            TaskStatus.PENDING_APPROVAL,
        ]
        self.fields["status"].choices = [
            (value, label)
            for value, label in self.fields["status"].choices
            if value in allowed_statuses
        ]
