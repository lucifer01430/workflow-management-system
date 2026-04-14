from django.shortcuts import redirect, render


def home_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    return render(request, "landing/home.html")