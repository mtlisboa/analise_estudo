from django.urls import path

from . import views

app_name = "organization-settings"

urlpatterns = [
    path("organizacoes/<int:pk>/configuracoes/", views.organization_settings, name="detail"),
]
