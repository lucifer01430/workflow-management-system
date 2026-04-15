from apps.auditlogs.models import AuditLog


def log_activity(actor=None, action="", target_model="", target_id=None, description=""):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_model=target_model,
        target_id=target_id,
        description=description,
    )