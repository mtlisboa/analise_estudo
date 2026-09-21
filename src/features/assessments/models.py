from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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


class Question(models.Model):
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Múltipla escolha"
        OPEN_ENDED = "open_ended", "Discursiva"

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="avaliação",
    )
    statement = models.TextField("enunciado")
    question_type = models.CharField(
        "formato da questão",
        max_length=24,
        choices=Type.choices,
        default=Type.MULTIPLE_CHOICE,
    )
    options = models.JSONField("alternativas", default=list, blank=True)
    correct_answer = models.TextField("gabarito ou resposta esperada", blank=True)
    explanation = models.TextField("explicação do gabarito", blank=True)
    points = models.DecimalField(
        "pontuação",
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    order = models.PositiveIntegerField("ordem", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("assessment", "order"),
                name="unique_question_order_per_assessment",
            )
        ]
        verbose_name = "questão"
        verbose_name_plural = "questões"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.options, list) or any(
            not isinstance(option, str) for option in self.options
        ):
            raise ValidationError({"options": "As alternativas devem formar uma lista de textos."})
        if self.question_type == self.Type.MULTIPLE_CHOICE:
            if len(self.options) < 2:
                raise ValidationError({"options": "Adicione pelo menos duas alternativas."})
            if self.correct_answer not in self.options:
                raise ValidationError(
                    {"correct_answer": "O gabarito deve corresponder a uma das alternativas."}
                )

    def __str__(self) -> str:
        return f"{self.assessment} · Questão {self.order}"
