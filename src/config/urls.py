from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("instituicao/montagem/", include("contexts.institutions.planning.urls")),
    path("instituicao/", include("contexts.institutions.urls")),
    path("provas-impressas/", include("features.paper_exams.urls")),
    path("admin/", admin.site.urls),
    path("assistente/", include("contexts.ia_integrations.urls")),
    path("analises/", include("features.analytics_dashboard.urls")),
    path("avaliacoes/", include("features.assessments.urls")),
    path("manager/", include("features.organization_settings.urls")),
    path("manager/", include("features.users_manager.urls")),
    path("", include("features.accounts.urls")),
]
