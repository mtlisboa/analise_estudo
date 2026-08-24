from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from .forms import LoginForm, OnboardingForm, SignUpForm, SysAdminLoginForm
from .models import User


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/landing.html")


class SessionLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        if not self.request.user.has_completed_onboarding:
            requested_url = self.get_redirect_url()
            if requested_url:
                self.request.session["onboarding_next"] = requested_url
            return str(reverse_lazy("accounts:onboarding"))
        return super().get_success_url()


class SysAdminLoginView(LoginView):
    authentication_form = SysAdminLoginForm
    template_name = "accounts/sysadmin_login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        return str(reverse_lazy("admin:index"))


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
        return redirect("accounts:onboarding")

    return render(request, "accounts/sign_up.html", {"form": form})


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    if not request.user.has_completed_onboarding and not request.user.is_system_admin:
        return redirect("accounts:onboarding")
    return render(request, "accounts/dashboard.html")


@login_required
def onboarding(request: HttpRequest) -> HttpResponse:
    if request.user.is_system_admin:
        return redirect("admin:index")
    if request.user.has_completed_onboarding:
        return redirect("accounts:dashboard")

    form = OnboardingForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        action = request.POST.get("action")
        if action not in {"start-test", "later"}:
            form.add_error(None, "Escolha iniciar o teste ou deixá-lo para depois.")
        else:
            user.diagnostic_test_choice = (
                User.DiagnosticTestChoice.STARTED
                if action == "start-test"
                else User.DiagnosticTestChoice.LATER
            )
            user.complete_onboarding()
            user.save()
            messages.success(request, "Seu perfil foi configurado.")

            if action == "start-test":
                return redirect(f'{reverse("ia-integrations:chat-bot")}?mode=diagnostic')
            return redirect(request.session.pop("onboarding_next", "accounts:dashboard"))

    return render(
        request,
        "accounts/onboarding.html",
        {"form": form, "onboarding_mode": True},
    )
