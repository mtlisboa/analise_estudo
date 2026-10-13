from django.apps import AppConfig


class CourseworkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contexts.institutions.coursework'
    label = 'institution_coursework'
    verbose_name = 'Provas e atividades por disciplina'
