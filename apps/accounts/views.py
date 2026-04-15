import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.forms import EmailLoginForm, OTPVerificationForm, RegisterForm
from apps.accounts.models import EmailOTP, RegistrationStatus, User
from apps.accounts.utils import create_and_send_otp

logger = logging.getLogger(__name__)


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = True
                    user.is_email_verified = False
                    user.is_active_by_admin = False
                    user.registration_status = RegistrationStatus.PENDING
                    user.set_password(form.cleaned_data["password"])
                    user.save()

                    create_and_send_otp(user)

                logger.info("Registration completed and OTP sent for user_id=%s email=%s", user.id, user.email)
                messages.success(
                    request,
                    "Registration successful. An OTP has been sent to your email address.",
                )
                return redirect("accounts:verify_otp", user_id=user.id)

            except Exception as exc:
                logger.exception("Registration failed during OTP delivery for email=%s: %s", form.cleaned_data.get("email"), exc)
                print(f"[REGISTER ERROR] email={form.cleaned_data.get('email')} error={exc}")
                messages.error(
                    request,
                    "Your account could not be registered because the OTP email could not be sent. "
                    "Please verify your email settings and try again.",
                )
        else:
            messages.error(request, "Please correct the highlighted errors and submit the form again.")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def verify_otp_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            otp_code = form.cleaned_data["otp_code"]

            otp_record = EmailOTP.objects.filter(
                user=user,
                otp_code=otp_code,
                is_used=False,
                expires_at__gte=timezone.now(),
            ).first()

            if otp_record:
                otp_record.is_used = True
                otp_record.save()

                user.is_email_verified = True
                user.save()

                messages.success(
                    request,
                    "Email verified successfully. Your account is pending admin approval.",
                )
                return redirect("accounts:login")
            else:
                messages.error(request, "Invalid or expired OTP. Please try again.")

    return render(request, "accounts/verify_otp.html", {"form": form, "user_obj": user})


def resend_otp_view(request, user_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user = get_object_or_404(User, id=user_id)

    if user.is_email_verified:
        messages.info(request, "This email address is already verified. Please log in.")
        return redirect("accounts:login")

    try:
        create_and_send_otp(user)
        logger.info("OTP resent successfully for user_id=%s email=%s", user.id, user.email)
        messages.success(request, f"A new OTP has been sent to {user.email}.")
    except Exception as exc:
        logger.exception("OTP resend failed for user_id=%s email=%s: %s", user.id, user.email, exc)
        print(f"[RESEND OTP ERROR] user_id={user.id} email={user.email} error={exc}")
        messages.error(
            request,
            "We could not resend the OTP right now. Please try again in a moment.",
        )

    return redirect("accounts:verify_otp", user_id=user.id)


class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm

    def form_valid(self, form):
        user = form.get_user()

        if not user.is_email_verified:
            messages.error(self.request, "Please verify your email before logging in.")
            return redirect("accounts:login")

        if not user.is_active_by_admin:
            messages.warning(
                self.request,
                "Your account is waiting for admin activation.",
            )
            return redirect("accounts:login")

        if user.registration_status != RegistrationStatus.APPROVED and not user.is_superuser:
            messages.warning(
                self.request,
                "Your registration is still pending approval.",
            )
            return redirect("accounts:login")

        login(self.request, user)
        messages.success(self.request, "Login successful.")
        return redirect("dashboard:home")


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("accounts:login")
