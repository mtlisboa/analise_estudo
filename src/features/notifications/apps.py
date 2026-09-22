from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "features.notifications"
    verbose_name = "Notificações"

    def ready(self):
        from . import signals  # noqa: F401
