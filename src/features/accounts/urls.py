from django.urls import path

from .views import (
    SessionLoginView,
    SessionLogoutView,
    SysAdminLoginView,
    dashboard,
    landing,
    onboarding,
    sign_up,
)

app_name = "accounts"

urlpatterns = [
    path("", landing, name="landing"),
    path("painel/", dashboard, name="dashboard"),
    path("conta/entrar/", SessionLoginView.as_view(), name="login"),
    path("conta/cadastro/", sign_up, name="sign-up"),
    path("conta/primeiros-passos/", onboarding, name="onboarding"),
    path("conta/sair/", SessionLogoutView.as_view(), name="logout"),
    path("sysadmin/entrar/", SysAdminLoginView.as_view(), name="sysadmin-login"),
]
