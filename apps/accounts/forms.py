from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import User, UserRole
from apps.departments.models import Department, Designation


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        validators=[validate_password],
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = User
        fields = [
            "employee_number",
            "full_name",
            "email",
            "username",
            "mobile_number",
            "department",
            "designation",
            "role",
            "profile_image",
        ]
        widgets = {
            "employee_number": forms.TextInput(attrs={"class": "form-control"}),
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "mobile_number": forms.TextInput(attrs={"class": "form-control"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "designation": forms.Select(attrs={"class": "form-select"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["designation"].queryset = Designation.objects.filter(is_active=True)
        self.fields["role"].choices = [
            (UserRole.HOD, "HOD"),
            (UserRole.EMPLOYEE, "Employee"),
            (UserRole.GENERAL_MANAGER, "General Manager"),
        ]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_employee_number(self):
        employee_number = self.cleaned_data.get("employee_number")
        if employee_number and User.objects.filter(employee_number=employee_number).exists():
            raise forms.ValidationError("This employee number is already in use.")
        return employee_number

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "full_name",
            "mobile_number",
            "profile_image",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter your full name"}),
            "mobile_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter your mobile number"}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }


class OTPVerificationForm(forms.Form):
    otp_code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter 6-digit OTP"})
    )


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Enter your email"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Enter your password"})
    )
