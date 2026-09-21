from django.urls import path

from . import views

app_name = "analytics-dashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("nova/", views.generate_analysis, name="generate"),
    path("<int:pk>/", views.analysis_detail, name="detail"),
]
