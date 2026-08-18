from django.urls import path

from .views import SessionLoginView, SessionLogoutView, dashboard, sign_up

app_name = "accounts"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("conta/entrar/", SessionLoginView.as_view(), name="login"),
    path("conta/cadastro/", sign_up, name="sign-up"),
    path("conta/sair/", SessionLogoutView.as_view(), name="logout"),
]
