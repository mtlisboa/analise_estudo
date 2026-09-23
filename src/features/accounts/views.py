from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from .forms import LoginForm, OnboardingForm, SignUpForm, SysAdminLoginForm
from .models import User
from .forms import ProfileForm, PreferencesForm, AvatarForm
from .avatar_service import change_avatar
from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/landing.html", {"public_page": True})


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



@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    action = request.POST.get("action") if request.method == "POST" else None
    if request.method == "POST" and action not in {"profile", "preferences", "password", "photo", "remove-photo"}:
        return HttpResponse("Ação inválida.", status=400)
    avatar_form = AvatarForm(request.POST if action == "photo" else None, request.FILES if action == "photo" else None)
    if action == "remove-photo" or (action == "photo" and avatar_form.is_valid()):
        change_avatar(request.user.pk, avatar_form.cleaned_data["photo"] if action == "photo" else None)
        messages.success(request, "Foto atualizada." if action == "photo" else "Foto removida.")
        return redirect("accounts:account")
    # Separate instances keep an invalid form from changing the displayed identity.
    profile_form = ProfileForm(request.POST if action == "profile" else None,
                               instance=User.objects.get(pk=request.user.pk))
    preferences_form = PreferencesForm(request.POST if action == "preferences" else None,
                                       instance=User.objects.get(pk=request.user.pk))
    password_form = PasswordChangeForm(request.user, request.POST if action == "password" else None)
    forms = {"profile": profile_form, "preferences": preferences_form, "password": password_form}
    if action in forms and forms[action].is_valid():
        user = forms[action].save()
        if action == "password":
            update_session_auth_hash(request, user)
        messages.success(request, {"profile": "Dados atualizados.", "preferences": "Preferências salvas.", "password": "Senha alterada com sucesso."}[action])
        return redirect("accounts:account")
    return render(request, "accounts/account.html", {
        "profile_form": profile_form, "preferences_form": preferences_form,
        "password_form": password_form, "avatar_form": avatar_form,
    })


@login_required
@require_POST
def update_theme(request):
    theme = request.POST.get("theme")
    if theme not in User.Theme.values:
        return JsonResponse({"error": "Tema inválido."}, status=400)
    User.objects.filter(pk=request.user.pk).update(theme_preference=theme)
    return JsonResponse({"theme": theme})


@login_required
@never_cache
@require_http_methods(["GET", "HEAD"])
def avatar(request):
    if not request.user.avatar:
        raise Http404
    try:
        response = FileResponse(request.user.avatar.open("rb"), content_type="image/jpeg")
    except FileNotFoundError:
        raise Http404
    response["X-Content-Type-Options"] = "nosniff"
    return response
