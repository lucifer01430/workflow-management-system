from django.urls import path

from apps.accounts.views import UserLoginView, logout_view, register_view, verify_otp_view

app_name = "accounts"

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("verify-otp/<int:user_id>/", verify_otp_view, name="verify_otp"),
]