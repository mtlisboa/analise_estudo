from django.apps import AppConfig


class CommunicationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contexts.institutions.communication'
    label = 'institution_communication'
    verbose_name = 'Comunicação institucional'
