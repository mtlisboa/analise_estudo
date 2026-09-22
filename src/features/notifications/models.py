from django.conf import settings
from django.db import models


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField("título", max_length=160)
    message = models.TextField("mensagem", max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-id",)
        indexes = [models.Index(fields=["recipient", "read_at", "-id"], name="notification_inbox_idx")]
        verbose_name = "notificação"
        verbose_name_plural = "notificações"

    def __str__(self):
        return self.title
