from django.apps import AppConfig

class AnalysisConfig(AppConfig):
    name = 'contexts.institutions.analysis'
    label = 'institution_analysis'
    verbose_name = 'Análise pedagógica institucional'

    def ready(self):
        from . import signals  # noqa: F401
