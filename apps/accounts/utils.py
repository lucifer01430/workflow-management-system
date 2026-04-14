import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import EmailOTP


def generate_otp():
    return str(random.randint(100000, 999999))


def create_and_send_otp(user):
    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    otp = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=10)

    EmailOTP.objects.create(
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
        f"Regards,\n"
        f"Workflow Management System"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )