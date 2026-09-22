from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class MembershipStatus(models.TextChoices):
    PENDING = "PENDING", "Pendente"
    ACTIVE = "ACTIVE", "Ativo"
    REJECTED = "REJECTED", "Recusado"
    REMOVED = "REMOVED", "Removido"


class Organization(models.Model):
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_organizations",
        verbose_name="responsável",
    )
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


def validate_school_document_size(document) -> None:
    if document.size > 10 * 1024 * 1024:
        raise ValidationError("Cada documento deve ter no máximo 10 MB.")


class SchoolApplication(models.Model):
    class SchoolType(models.TextChoices):
        PUBLIC = "PUBLIC", "Pública"
        PRIVATE = "PRIVATE", "Privada"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        APPROVED = "APPROVED", "Aprovada"
        REJECTED = "REJECTED", "Rejeitada"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="school_applications",
        verbose_name="gestor solicitante",
    )
    legal_name = models.CharField("razão social", max_length=180)
    display_name = models.CharField("nome da escola", max_length=180)
    school_type = models.CharField("tipo", max_length=10, choices=SchoolType.choices)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True)
    inep_code = models.CharField("código INEP", max_length=12, blank=True)
    address = models.CharField("endereço", max_length=240)
    city = models.CharField("cidade", max_length=120)
    state = models.CharField("UF", max_length=2)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    review_notes = models.TextField("parecer", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_school_applications",
        verbose_name="revisada por",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField("revisada em", null=True, blank=True)
    approved_school = models.OneToOneField(
        "School",
        on_delete=models.SET_NULL,
        related_name="source_application",
        verbose_name="escola aprovada",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("enviada em", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "solicitação de escola"
        verbose_name_plural = "solicitações de escolas"

    def clean(self) -> None:
        self.cnpj = self.cnpj.strip()
        self.inep_code = self.inep_code.strip()
        self.state = self.state.strip().upper()
        if not self.cnpj and not self.inep_code:
            raise ValidationError("Informe o CNPJ ou o código INEP da escola.")

    def __str__(self) -> str:
        return f"{self.display_name} · {self.get_status_display()}"


class School(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.PROTECT,
        related_name="school",
        verbose_name="organização operacional",
    )
    legal_name = models.CharField("razão social", max_length=180)
    display_name = models.CharField("nome da escola", max_length=180)
    school_type = models.CharField(
        "tipo", max_length=10, choices=SchoolApplication.SchoolType.choices
    )
    cnpj = models.CharField("CNPJ", max_length=18, blank=True, unique=True, null=True)
    inep_code = models.CharField(
        "código INEP", max_length=12, blank=True, unique=True, null=True
    )
    address = models.CharField("endereço", max_length=240)
    city = models.CharField("cidade", max_length=120)
    state = models.CharField("UF", max_length=2)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_schools",
        verbose_name="aprovada por",
    )
    approved_at = models.DateTimeField("aprovada em", default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("display_name",)
        verbose_name = "escola credenciada"
        verbose_name_plural = "escolas credenciadas"

    def __str__(self) -> str:
        return self.display_name


class SchoolVerificationDocument(models.Model):
    application = models.ForeignKey(
        SchoolApplication,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="solicitação",
    )
    file = models.FileField(
        "arquivo",
        upload_to="school_applications/%Y/%m/",
        validators=(
            FileExtensionValidator(("pdf", "jpg", "jpeg", "png")),
            validate_school_document_size,
        ),
    )
    original_name = models.CharField("nome original", max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)
        verbose_name = "documento comprobatório"
        verbose_name_plural = "documentos comprobatórios"

    def __str__(self) -> str:
        return self.original_name


class OrganizationMembership(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="organização",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        verbose_name="usuário",
    )
    is_teacher = models.BooleanField("professor", default=False)
    is_student = models.BooleanField("aluno", default=False)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="organization_members_added",
        verbose_name="adicionado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("user__username",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"),
                name="unique_user_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(is_teacher=True) | Q(is_student=True),
                name="organization_member_has_educational_role",
            ),
        ]

    def clean(self) -> None:
        if not self.is_teacher and not self.is_student:
            raise ValidationError("O membro deve ser professor, aluno ou ambos.")

    @property
    def roles_display(self) -> str:
        roles = []
        if self.is_teacher:
            roles.append("Professor")
        if self.is_student:
            roles.append("Aluno")
        return " e ".join(roles)

    def __str__(self) -> str:
        return f"{self.user} em {self.organization} ({self.roles_display})"


class ClassroomGroup(models.Model):
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="classroom_groups",
        verbose_name="organização",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="grupo pai",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_classroom_groups",
        verbose_name="criado por",
    )
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_classroom_group_name_per_organization",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} · {self.organization}"

    def clean(self) -> None:
        if not self.parent_id:
            return
        if self.parent_id == self.pk:
            raise ValidationError("Um grupo não pode ser pai de si mesmo.")
        if self.organization_id and self.parent.organization_id != self.organization_id:
            raise ValidationError("O grupo pai deve pertencer à mesma instituição.")
        ancestor = self.parent
        visited = {self.pk} if self.pk else set()
        while ancestor is not None:
            if ancestor.pk in visited:
                raise ValidationError("A hierarquia de grupos não pode conter ciclos.")
            visited.add(ancestor.pk)
            ancestor = ancestor.parent


class EducationalRelationship(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teaching_relationships",
        verbose_name="professor",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_relationships",
        verbose_name="aluno",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="relationship_requests",
        verbose_name="solicitado por",
    )
    status = models.CharField(
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("teacher", "student"),
                name="unique_teacher_student_relationship",
            ),
            models.CheckConstraint(
                condition=~Q(teacher=F("student")),
                name="teacher_and_student_must_differ",
            ),
            models.CheckConstraint(
                condition=Q(requested_by=F("teacher")) | Q(requested_by=F("student")),
                name="relationship_requester_is_participant",
            ),
        ]

    def clean(self) -> None:
        if self.teacher_id == self.student_id:
            raise ValidationError("Professor e aluno devem ser usuários diferentes.")
        if self.requested_by_id not in {self.teacher_id, self.student_id}:
            raise ValidationError("A solicitação deve ser iniciada por um dos participantes.")

    @property
    def recipient_id(self) -> int:
        return self.student_id if self.requested_by_id == self.teacher_id else self.teacher_id

    def __str__(self) -> str:
        return f"{self.teacher} → {self.student}"


class Classroom(models.Model):
    class Shift(models.TextChoices):
        MORNING = "MORNING", "Manhã"
        AFTERNOON = "AFTERNOON", "Tarde"
        EVENING = "EVENING", "Noite"
        FULL_TIME = "FULL_TIME", "Integral"

    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="classrooms",
        verbose_name="organização",
    )
    group = models.ForeignKey(
        ClassroomGroup,
        on_delete=models.CASCADE,
        related_name="classrooms",
        verbose_name="grupo de turmas",
    )
    letter = models.CharField("letra", max_length=10, blank=True)
    shift = models.CharField(
        "turno",
        max_length=10,
        choices=Shift.choices,
        default=Shift.MORNING,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_classrooms",
        verbose_name="responsável",
    )
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("shift", "letter", "name")

    def __str__(self) -> str:
        return f"{self.name} · {self.organization}"


class ClassroomMembership(models.Model):
    class Role(models.TextChoices):
        TEACHER = "TEACHER", "Professor"
        STUDENT = "STUDENT", "Aluno"

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="turma",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classroom_memberships",
        verbose_name="usuário",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    status = models.CharField(
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.PENDING,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classroom_invitations",
        verbose_name="convidado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("role", "user__username")
        constraints = [
            models.UniqueConstraint(
                fields=("classroom", "user"),
                name="unique_user_per_classroom",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} em {self.classroom} ({self.get_role_display()})"


class ClassroomTest(models.Model):
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="tests",
        verbose_name="turma",
    )
    title = models.CharField("título", max_length=160)
    instructions = models.TextField("instruções", blank=True)
    max_score = models.PositiveSmallIntegerField(
        "pontuação máxima",
        default=10,
        validators=(MinValueValidator(1),),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_classroom_tests",
        verbose_name="criado por",
    )
    is_published = models.BooleanField("publicado", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} · {self.classroom}"


class SelfAssessment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="self_assessments",
        verbose_name="usuário",
    )
    focus = models.PositiveSmallIntegerField(
        "foco", validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    organization = models.PositiveSmallIntegerField(
        "organização", validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    comprehension = models.PositiveSmallIntegerField(
        "compreensão", validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    motivation = models.PositiveSmallIntegerField(
        "motivação", validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at",)

    @property
    def score(self) -> int:
        values = (self.focus, self.organization, self.comprehension, self.motivation)
        return round(sum(values) / len(values) * 20)

    def __str__(self) -> str:
        return f"Autoavaliação de {self.user} ({self.created_at:%d/%m/%Y})"
