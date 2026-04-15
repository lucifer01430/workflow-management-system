import logging
import random
import smtplib
import socket
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from apps.accounts.models import EmailOTP

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
    message = (
        f"Hello {user.full_name},\n\n"
        f"Your OTP is: {otp}\n"
        f"This OTP is valid for 10 minutes.\n\n"
        f"If you did not request this registration, please ignore this email.\n\n"
        f"Regards,\n"
        f"Workflow Management System"
    )

    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

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
