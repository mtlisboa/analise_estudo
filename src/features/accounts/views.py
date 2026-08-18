from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import LoginForm, SignUpForm


class SessionLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class SessionLogoutView(LogoutView):
    http_method_names = ["post", "options"]
    next_page = reverse_lazy("accounts:login")


def sign_up(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Conta criada com sucesso.")
        return redirect("accounts:dashboard")

    return render(request, "accounts/sign_up.html", {"form": form})


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/dashboard.html")
