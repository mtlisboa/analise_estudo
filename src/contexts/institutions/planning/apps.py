from django.apps import AppConfig


class PlanningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contexts.institutions.planning"
    label = "institution_planning"
    verbose_name = "Montagem de turmas"
