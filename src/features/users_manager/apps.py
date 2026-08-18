from django.apps import AppConfig


class UsersManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "features.users_manager"
    verbose_name = "Gestão de usuários"
