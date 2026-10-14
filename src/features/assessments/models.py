from .diagnostics import validate_metadata
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
    class Delivery(models.TextChoices):
        ONLINE = 'online', 'Área do aluno'
        PRINTED = 'printed', 'Impressa'

    delivery_mode = models.CharField('aplicação', max_length=10, choices=Delivery.choices, default=Delivery.ONLINE)
    due_at = models.DateTimeField('data de entrega', null=True, blank=True)
    is_visible = models.BooleanField('visível aos alunos', default=False)
    is_finalized = models.BooleanField('aplicação física finalizada', default=False)

    class AssemblyMethod(models.TextChoices):
        MANUAL = "manual", "Montagem manual"
        ALGORITHMIC = "algorithmic", "Montagem algorítmica"
        AI_CURATED = "ai_curated", "Montagem via IA com banco existente"
        AI_GENERATED = "ai_generated", "Criação completa das questões via IA"

    class AssemblyStatus(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        READY = "ready", "Pronta"
        FAILED = "failed", "Falha na montagem"

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
    assembly_method = models.CharField(
        "forma de montagem",
        max_length=20,
        choices=AssemblyMethod.choices,
        default=AssemblyMethod.MANUAL,
    )
    desired_question_count = models.PositiveSmallIntegerField(
        "quantidade desejada de questões", default=0
    )
    generation_prompt = models.TextField("instruções para montagem", blank=True)
    assembly_status = models.CharField(
        "status da montagem",
        max_length=10,
        choices=AssemblyStatus.choices,
        default=AssemblyStatus.DRAFT,
    )
    assembly_notes = models.TextField("resultado da montagem", blank=True)
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


class QuestionBankItem(models.Model):
    title = models.CharField("título", max_length=160, blank=True)

    @property
    def display_title(self):
        return self.title or f"{self.topic} · {self.statement[:75]}"

    diagnostic_metadata = models.JSONField("metadados pedagógicos", default=dict, blank=True, validators=[validate_metadata])
    class Visibility(models.TextChoices):
        INSTITUTION = "institution", "Somente a instituição"
        INSTITUTIONS = "institutions", "Professores e gestores de outras instituições"
        EVERYONE = "everyone", "Todos os usuários cadastrados"

    external_visibility = models.CharField(
        "Disponibilidade externa", max_length=16, choices=Visibility.choices,
        default=Visibility.INSTITUTION,
    )
    sharing_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_question_shares", verbose_name="liberado por",
    )
    sharing_approved_at = models.DateTimeField(null=True, blank=True)

    organization = models.ForeignKey(
        "users_manager.Organization", on_delete=models.CASCADE,
        related_name="shared_questions", null=True, blank=True,
        verbose_name="instituição",
    )
    source_key = models.CharField(max_length=100, blank=True)
    source_url = models.URLField(blank=True, max_length=500)
    source_metadata = models.JSONField(default=dict, blank=True)

    class CreationMethod(models.TextChoices):
        MANUAL = "manual", "Criação manual"
        DERIVED = "derived", "Edição de questão existente"
        AI_EDITED = "ai_edited", "Questão existente editada por IA"
        AI_GENERATED = "ai_generated", "Questão nova gerada por IA"
        IMPORTED = "imported", "Base externa"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="question_bank_items",
        verbose_name="responsável",
    )
    subject = models.CharField("matéria", max_length=120)
    topic = models.CharField("assunto", max_length=160)
    support_text = models.TextField("texto de apoio", blank=True)
    images = models.ManyToManyField("QuestionImage", blank=True, related_name="bank_items")
    statement = models.TextField("comando / enunciado")
    question_type = models.CharField(
        "formato da questão",
        max_length=24,
        choices=(
            ("multiple_choice", "Múltipla escolha"),
            ("open_ended", "Discursiva"),
        ),
        default="multiple_choice",
    )
    options = models.JSONField("alternativas", default=list, blank=True)
    correct_answer = models.TextField("gabarito ou resposta esperada", blank=True)
    explanation = models.TextField("explicação do gabarito", blank=True)
    default_points = models.DecimalField(
        "pontuação padrão",
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    creation_method = models.CharField(
        "origem",
        max_length=16,
        choices=CreationMethod.choices,
        default=CreationMethod.MANUAL,
    )
    source_question = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="derived_questions",
        verbose_name="questão de origem",
        null=True,
        blank=True,
    )
    ai_instructions = models.TextField("instruções enviadas à IA", blank=True)
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "questão do banco"
        verbose_name_plural = "banco de questões"
        constraints = [models.CheckConstraint(
            condition=models.Q(external_visibility="institution") | models.Q(organization__isnull=False),
            name="external_questions_require_institution",
        ), models.UniqueConstraint(
            fields=("organization", "source_key"),
            condition=~models.Q(source_key=""), name="unique_institution_source_question",
        )]

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.options, list) or any(
            not isinstance(option, str) for option in self.options
        ):
            raise ValidationError({"options": "As alternativas devem formar uma lista de textos."})
        if self.question_type == "multiple_choice":
            if len(self.options) < 2:
                raise ValidationError({"options": "Adicione pelo menos duas alternativas."})
            if self.correct_answer not in self.options:
                raise ValidationError(
                    {"correct_answer": "O gabarito deve corresponder a uma das alternativas."}
                )

    def __str__(self) -> str:
        return f"{self.subject} · {self.topic} · {self.statement[:55]}"


class Question(models.Model):
    diagnostic_metadata = models.JSONField("metadados pedagógicos", default=dict, blank=True, validators=[validate_metadata])
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Múltipla escolha"
        OPEN_ENDED = "open_ended", "Discursiva"

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="avaliação",
    )
    bank_item = models.ForeignKey(
        QuestionBankItem,
        on_delete=models.SET_NULL,
        related_name="assessment_copies",
        verbose_name="item do banco",
        null=True,
        blank=True,
    )
    support_text = models.TextField("texto de apoio", blank=True)
    images = models.ManyToManyField("QuestionImage", blank=True, related_name="questions")
    statement = models.TextField("comando / enunciado")
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


def question_image_path(instance, filename):
    from uuid import uuid4
    return f'question_images/{instance.owner_id}/{uuid4().hex}.png'


class QuestionImage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.ImageField(upload_to=question_image_path)
    description = models.CharField('descrição da imagem', max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('pk',)

    def __str__(self):
        return self.description
