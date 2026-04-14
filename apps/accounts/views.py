from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from apps.accounts.forms import EmailLoginForm, OTPVerificationForm, RegisterForm
from apps.accounts.models import EmailOTP, RegistrationStatus, User
from apps.accounts.utils import create_and_send_otp


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True
            user.is_email_verified = False
            user.is_active_by_admin = False
            user.registration_status = RegistrationStatus.PENDING
            user.set_password(form.cleaned_data["password"])
            user.save()

            create_and_send_otp(user)

            messages.success(request, "Registration successful. Please verify your email using the OTP sent to your email.")
            return redirect("accounts:verify_otp", user_id=user.id)
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