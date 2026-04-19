import logging
import random
import smtplib
import socket
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from apps.auditlogs.utils import log_activity
from apps.accounts.models import EmailOTP, RegistrationStatus, User, UserRole
from apps.notifications.models import NotificationType
from apps.notifications.utils import create_notification, send_action_email

logger = logging.getLogger(__name__)


def generate_otp():
    return str(random.randint(100000, 999999))


def create_and_send_otp(user):
    """
    Create a fresh OTP and send it to the user's email address.

    Raises the underlying mail exception when delivery fails so the caller
    can decide whether to retry, rollback, or show a UI message.
    """
    logger.info("Starting OTP generation for user_id=%s email=%s", user.id, user.email)

    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    otp = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=10)

    otp_record = EmailOTP.objects.create(
        user=user,
        otp_code=otp,
        expires_at=expires_at,
        is_used=False,
    )

    subject = "Your OTP for Workflow Management System"
    context = {
        "recipient_name": user.full_name or user.username,
        "otp": otp,
        "expires_in_minutes": 10,
        "software_name": "Workflow Management System",
        "support_note": "If you did not request this registration, please ignore this email.",
    }
    text_message = render_to_string("emails/otp_email.txt", context)
    html_message = render_to_string("emails/otp_email.html", context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(html_message, "text/html")

    max_attempts = 2
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        connection = None
        try:
            logger.info(
                "Sending OTP email attempt=%s/%s for user_id=%s email=%s via host=%s port=%s tls=%s ssl=%s",
                attempt,
                max_attempts,
                user.id,
                user.email,
                settings.EMAIL_HOST,
                settings.EMAIL_PORT,
                settings.EMAIL_USE_TLS,
                settings.EMAIL_USE_SSL,
            )
            connection = get_connection(
                backend=settings.EMAIL_BACKEND,
                fail_silently=False,
                timeout=getattr(settings, "EMAIL_TIMEOUT", 10),
            )
            email.connection = connection
            sent_count = email.send(fail_silently=False)

            if sent_count != 1:
                logger.error(
                    "OTP email send returned unexpected count=%s for user_id=%s email=%s",
                    sent_count,
                    user.id,
                    user.email,
                )
                raise RuntimeError("OTP email was not sent successfully.")

            logger.info("OTP email sent successfully for user_id=%s email=%s", user.id, user.email)
            return otp_record

        except (
            PermissionError,
            smtplib.SMTPException,
            socket.timeout,
            TimeoutError,
            ConnectionError,
            OSError,
            RuntimeError,
        ) as exc:
            last_exception = exc
            logger.exception(
                "OTP email send failed on attempt=%s for user_id=%s email=%s: %s",
                attempt,
                user.id,
                user.email,
                exc,
            )
            print(
                f"[OTP EMAIL ERROR] attempt={attempt} user_id={user.id} "
                f"email={user.email} error={type(exc).__name__}: {exc}"
            )
            if attempt < max_attempts:
                time.sleep(1)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    logger.debug("Ignoring SMTP connection close failure", exc_info=True)

    raise last_exception


def get_reporting_contacts(user):
    reporting_hod = None
    reporting_gm = None

    gm_queryset = User.objects.filter(
        role=UserRole.GENERAL_MANAGER,
        is_active=True,
        is_active_by_admin=True,
        registration_status=RegistrationStatus.APPROVED,
    ).select_related("department", "designation")

    if user.role == UserRole.EMPLOYEE:
        if (
            user.department
            and user.department.hod
            and user.department.hod.is_active
            and user.department.hod.is_active_by_admin
            and user.department.hod.registration_status == RegistrationStatus.APPROVED
        ):
            reporting_hod = user.department.hod
        reporting_gm = gm_queryset.first()
    elif user.role == UserRole.HOD:
        reporting_gm = gm_queryset.first()

    return reporting_hod, reporting_gm


def approve_user_account(*, user, approved_by):
    user.registration_status = RegistrationStatus.APPROVED
    user.is_active = True
    user.is_active_by_admin = True
    user.approved_by = approved_by
    user.approved_at = timezone.now()
    user.rejection_reason = ""
    user.save(
        update_fields=[
            "is_active",
            "registration_status",
            "is_active_by_admin",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
    )

    create_notification(
        recipient=user,
        title="Account Approved",
        message="Your account has been approved and is now active.",
        notification_type=NotificationType.ACCOUNT_APPROVED,
    )
    send_action_email(
        subject="Account Approved",
        message="Your account has been approved.",
        recipient_list=[user.email] if user.email else [],
        html_template="emails/account_approved_email.html",
        text_template="emails/account_approved_email.txt",
        context={
            "subject": "Account Approved",
            "heading": "Account approved",
            "recipient_name": user.full_name or user.username,
            "email": user.email,
            "role": user.get_role_display(),
            "department": user.department or "-",
            "action_copy": "You can now sign in and access your workflow dashboard.",
        },
    )
    log_activity(
        actor=approved_by,
        action="account_approved",
        target_model="User",
        target_id=user.id,
        description=f"Account approved for '{user.email}'.",
    )
    return user


def reject_user_account(*, user, rejected_by, reason=""):
    user.registration_status = RegistrationStatus.REJECTED
    user.is_active_by_admin = False
    user.approved_by = None
    user.approved_at = None
    user.rejection_reason = reason or "No reason provided"
    user.save(
        update_fields=[
            "registration_status",
            "is_active_by_admin",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
    )

    create_notification(
        recipient=user,
        title="Account Rejected",
        message="Your account request could not be approved.",
        notification_type=NotificationType.ACCOUNT_REJECTED,
    )
    send_action_email(
        subject="Account Rejected",
        message="Your account has been rejected.",
        recipient_list=[user.email] if user.email else [],
        html_template="emails/account_rejected_email.html",
        text_template="emails/account_rejected_email.txt",
        context={
            "subject": "Account Rejected",
            "heading": "Account rejected",
            "recipient_name": user.full_name or user.username,
            "email": user.email,
            "rejection_reason": reason or "No reason provided",
            "action_copy": "Please contact the administrator if you need clarification or a revised account request.",
        },
    )
    log_activity(
        actor=rejected_by,
        action="account_rejected",
        target_model="User",
        target_id=user.id,
        description=f"Account rejected for '{user.email}'. Reason: {reason or 'No reason provided'}",
    )
    return user
