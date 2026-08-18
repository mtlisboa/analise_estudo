from django.urls import path

from . import views

app_name = "users-manager"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("vinculos/novo/", views.request_relationship, name="relationship-create"),
    path(
        "vinculos/<int:pk>/<str:decision>/",
        views.decide_relationship,
        name="relationship-decide",
    ),
    path("turmas/nova/", views.create_classroom, name="classroom-create"),
    path("turmas/<int:pk>/", views.classroom_detail, name="classroom-detail"),
    path(
        "turmas/<int:pk>/convidar/",
        views.invite_classroom_member,
        name="classroom-invite",
    ),
    path(
        "convites/<int:pk>/<str:decision>/",
        views.decide_classroom_invitation,
        name="classroom-invitation-decide",
    ),
    path("autoavaliacoes/nova/", views.create_self_assessment, name="assessment-create"),
]
