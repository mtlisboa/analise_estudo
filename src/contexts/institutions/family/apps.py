from django.apps import AppConfig


class FamilyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contexts.institutions.family'
    label = 'institution_family'
    verbose_name = 'Famílias e atendimento'

    def ready(self):
        from . import signals  # noqa: F401
