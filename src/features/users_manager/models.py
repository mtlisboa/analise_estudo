from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class MembershipStatus(models.TextChoices):
    PENDING = "PENDING", "Pendente"
    ACTIVE = "ACTIVE", "Ativo"
    REJECTED = "REJECTED", "Recusado"
    REMOVED = "REMOVED", "Removido"


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
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_classrooms",
        verbose_name="responsável",
    )
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


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
