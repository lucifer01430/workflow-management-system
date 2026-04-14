from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import EmailOTP, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

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

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "otp_code", "created_at", "expires_at", "is_used")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "otp_code")
    ordering = ("-created_at",)