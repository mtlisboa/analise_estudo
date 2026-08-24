from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("", views.index, name="index"),
    path("nova/", views.create, name="create"),
    path("<int:pk>/editar/", views.update, name="update"),
]
