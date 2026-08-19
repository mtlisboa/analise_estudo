from django.urls import path

from . import views

app_name = "users-manager"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("organizacoes/nova/", views.create_organization, name="organization-create"),
    path("organizacoes/<int:pk>/", views.organization_detail, name="organization-detail"),
    path(
        "organizacoes/<int:pk>/membros/novo/",
        views.add_organization_member,
        name="organization-member-add",
    ),
    path("vinculos/novo/", views.request_relationship, name="relationship-create"),
    path(
        "vinculos/<int:pk>/<str:decision>/",
        views.decide_relationship,
        name="relationship-decide",
    ),
    path(
        "organizacoes/<int:organization_pk>/turmas/nova/",
        views.create_classroom,
        name="classroom-create",
    ),
    path("turmas/<int:pk>/", views.classroom_detail, name="classroom-detail"),
    path(
        "turmas/<int:pk>/convidar/",
        views.invite_classroom_member,
        name="classroom-invite",
    ),
    path("turmas/<int:pk>/testes/novo/", views.create_classroom_test, name="classroom-test-create"),
    path(
        "convites/<int:pk>/<str:decision>/",
        views.decide_classroom_invitation,
        name="classroom-invitation-decide",
    ),
    path("autoavaliacoes/nova/", views.create_self_assessment, name="assessment-create"),
]
