from django.urls import path
from . import views

app_name = "planning"
urlpatterns = [
    path("", views.index, name="index"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/acao/<str:action>/", views.action, name="action"),
    path("<int:pk>/<str:kind>/novo/", views.edit, name="create"),
    path("<int:pk>/<str:kind>/<int:item>/editar/", views.edit, name="edit"),
    path("<int:pk>/<str:kind>/<int:item>/excluir/", views.delete, name="delete"),
]
