from django.urls import path

from . import views

app_name = "users-manager"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("escolas/solicitar/", views.create_school_application, name="school-application-create"),
    path(
        "escolas/documentos/<int:pk>/",
        views.download_school_document,
        name="school-document-download",
    ),
    path(
        "instituicoes/exportacoes/<int:pk>/",
        views.download_institution_export,
        name="institution-export-download",
    ),
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
    path(
        "organizacoes/<int:organization_pk>/grupos/novo/",
        views.create_classroom_group,
        name="classroom-group-create",
    ),
    path(
        "grupos/<int:pk>/",
        views.classroom_group_detail,
        name="classroom-group-detail",
    ),
    path(
        "grupos/<int:group_pk>/turmas/nova/",
        views.create_classroom,
        name="group-classroom-create",
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
