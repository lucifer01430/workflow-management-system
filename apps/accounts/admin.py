from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import EmailOTP, User
from apps.accounts.utils import approve_user_account, reject_user_account


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    actions = ("approve_selected_users", "reject_selected_users")

    list_display = (
        "id",
        "email",
        "username",
        "full_name",
        "employee_number",
        "department",
        "designation",
        "role",
        "is_active",
        "is_active_by_admin",
        "is_email_verified",
        "registration_status",
        "approved_by",
        "approved_at",
        "is_staff",
    )
    list_filter = (
        "role",
        "department",
        "designation",
        "is_active",
        "is_active_by_admin",
        "is_email_verified",
        "registration_status",
        "is_staff",
        "is_superuser",
    )
    search_fields = ("email", "username", "full_name", "employee_number", "mobile_number")
    ordering = ("id",)

    fieldsets = (
        ("Login Credentials", {
            "fields": ("email", "username", "password")
        }),
        ("Personal Information", {
      "fields": (
        "full_name",
        "employee_number",
        "mobile_number",
        "department",
        "designation",
        "profile_image",
        "role",
            )
        }),
        ("Permissions", {
    "fields": (
        "is_active",
        "is_active_by_admin",
        "is_email_verified",
        "registration_status",
        "approved_by",
        "approved_at",
        "rejection_reason",
        "is_staff",
        "is_superuser",
        "groups",
        "user_permissions",
    )
}),
        ("Important Dates", {
            "fields": ("last_login", "date_joined")
        }),
    )

    add_fieldsets = (
        ("Create User", {
            "classes": ("wide",),
            "fields": (
                "email",
                "username",
                "full_name",
                "employee_number",
                "mobile_number",
                "department",
                "designation",
                "role",
                "password1",
                "password2",
                "is_active",
                "is_active_by_admin",
                "is_email_verified",
                "registration_status",
                "is_staff",
                "is_superuser",
            ),
        }),
    )

    @admin.action(description="Approve selected users")
    def approve_selected_users(self, request, queryset):
        approved_count = 0
        for user in queryset:
            if user.registration_status == "approved" and user.is_active_by_admin:
                continue
            approve_user_account(user=user, approved_by=request.user)
            approved_count += 1

        if approved_count:
            self.message_user(
                request,
                f"Approved {approved_count} user account(s) and sent the related notifications.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "No selected users required approval changes.",
                level=messages.INFO,
            )

    @admin.action(description="Reject selected users")
    def reject_selected_users(self, request, queryset):
        rejected_count = 0
        for user in queryset:
            if user.registration_status == "rejected" and not user.is_active_by_admin:
                continue
            reject_user_account(
                user=user,
                rejected_by=request.user,
                reason=user.rejection_reason or "Rejected by administrator review.",
            )
            rejected_count += 1

        if rejected_count:
            self.message_user(
                request,
                f"Rejected {rejected_count} user account(s) and sent the related notifications.",
                level=messages.WARNING,
            )
        else:
            self.message_user(
                request,
                "No selected users required rejection changes.",
                level=messages.INFO,
            )

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = (
                User.objects.filter(pk=obj.pk)
                .values_list("registration_status", flat=True)
                .first()
            )

        super().save_model(request, obj, form, change)

        if not change or previous_status == obj.registration_status:
            return

        if obj.registration_status == "approved":
            approve_user_account(user=obj, approved_by=request.user)
        elif obj.registration_status == "rejected":
            reject_user_account(
                user=obj,
                rejected_by=request.user,
                reason=obj.rejection_reason or "Rejected by administrator review.",
            )

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "otp_code", "created_at", "expires_at", "is_used")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "otp_code")
    ordering = ("-created_at",)
