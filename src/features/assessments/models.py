from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AssessmentTechnique(models.Model):
    code = models.SlugField("código", max_length=50, unique=True)
    name = models.CharField("nome", max_length=100)
    description = models.CharField("descrição", max_length=240, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "técnica avaliativa"
        verbose_name_plural = "técnicas avaliativas"

    def __str__(self) -> str:
        return self.name


class AssessmentType(models.Model):
    code = models.SlugField("código", max_length=50, unique=True)
    name = models.CharField("nome", max_length=100)
    description = models.CharField("descrição", max_length=240, blank=True)
    default_technique = models.ForeignKey(
        AssessmentTechnique,
        on_delete=models.PROTECT,
        related_name="default_for_types",
        verbose_name="técnica padrão",
    )

    class Meta:
        ordering = ("pk",)
        verbose_name = "tipo de questão avaliativa"
        verbose_name_plural = "tipos de questão avaliativa"

    def __str__(self) -> str:
        return self.name


class Assessment(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_assessments",
        verbose_name="responsável",
    )
    subject = models.CharField("matéria", max_length=120)
    topic = models.CharField("assunto", max_length=160)
    observations = models.JSONField("observações e restrições", default=list, blank=True)
    assessment_types = models.ManyToManyField(
        AssessmentType,
        related_name="assessments",
        verbose_name="tipos de questão avaliativa",
    )
    technique = models.ForeignKey(
        AssessmentTechnique,
        on_delete=models.PROTECT,
        related_name="assessments",
        verbose_name="técnica avaliativa",
    )
    technique_selected_automatically = models.BooleanField(
        "técnica selecionada automaticamente",
        default=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.observations, list) or any(
            not isinstance(item, str) for item in self.observations
        ):
            raise ValidationError(
                {"observations": "As observações e restrições devem formar uma lista de textos."}
            )

    def __str__(self) -> str:
        return f"{self.subject} — {self.topic}"
