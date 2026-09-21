from django.conf import settings
from django.db import models


class SavedAnalysis(models.Model):
    title = models.CharField("título", max_length=160)
    scope_title = models.CharField("escopo", max_length=160)
    period_label = models.CharField("período", max_length=80)
    filters = models.JSONField("filtros", default=dict)
    snapshot = models.JSONField("resultado", default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_analyses",
        verbose_name="criado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} · {self.created_by}"
