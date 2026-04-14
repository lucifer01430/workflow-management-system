from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = (
        "id",
        "email",
        "username",
        "full_name",
        "employee_number",
        "role",
        "is_active",
        "is_active_by_admin",
        "is_email_verified",
        "is_staff",
    )
    list_filter = (
        "role",
        "is_active",
        "is_active_by_admin",
        "is_email_verified",
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
            "fields": ("full_name", "employee_number", "mobile_number", "profile_image", "role")
        }),
        ("Permissions", {
            "fields": ("is_active", "is_active_by_admin", "is_email_verified", "is_staff", "is_superuser", "groups", "user_permissions")
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
                "role",
                "password1",
                "password2",
                "is_active",
                "is_active_by_admin",
                "is_email_verified",
                "is_staff",
                "is_superuser",
            ),
        }),
    )