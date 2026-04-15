from django.contrib import admin

from apps.auditlogs.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "actor",
        "action",
        "target_model",
        "target_id",
        "created_at",
    )
    list_filter = ("action", "target_model", "created_at")
    search_fields = ("actor__email", "actor__full_name", "action", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("actor",)