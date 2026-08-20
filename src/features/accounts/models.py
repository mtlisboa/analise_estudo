from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Usuário extensível da aplicação."""

    class SystemRole(models.TextChoices):
        MEMBER = "MEMBER", "Usuário"
        MANAGER = "MANAGER", "Gestor"
        ADMIN = "ADMIN", "Administrador"
        SYSADMIN = "SYSADMIN", "Administrador de sistema"

    class OnboardingRole(models.TextChoices):
        STUDENT = "STUDENT", "Aluno"
        TEACHER = "TEACHER", "Professor"
        MANAGER = "MANAGER", "Gestor educacional"
        GUARDIAN = "GUARDIAN", "Responsável por aluno"
        OTHER = "OTHER", "Outro"

    class DiscoverySource(models.TextChoices):
        RECOMMENDATION = "RECOMMENDATION", "Indicação de alguém"
        SOCIAL_MEDIA = "SOCIAL_MEDIA", "Redes sociais"
        SEARCH = "SEARCH", "Pesquisa na internet"
        SCHOOL = "SCHOOL", "Escola ou faculdade"
        WORK = "WORK", "Trabalho"
        EVENT = "EVENT", "Evento ou comunidade"
        OTHER = "OTHER", "Outro"

    class EducationLevel(models.TextChoices):
        ELEMENTARY = "ELEMENTARY", "Ensino fundamental"
        HIGH_SCHOOL = "HIGH_SCHOOL", "Ensino médio"
        TECHNICAL = "TECHNICAL", "Ensino técnico"
        UNDERGRADUATE = "UNDERGRADUATE", "Graduação"
        POSTGRADUATE = "POSTGRADUATE", "Pós-graduação"
        OTHER = "OTHER", "Outro"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefiro não informar"

    class AppGoal(models.TextChoices):
        IMPROVE_PERFORMANCE = "IMPROVE_PERFORMANCE", "Melhorar meu desempenho"
        ORGANIZE_STUDIES = "ORGANIZE_STUDIES", "Organizar meus estudos"
        PREPARE_EXAM = "PREPARE_EXAM", "Preparar-me para uma prova"
        TEACH_OR_MANAGE = "TEACH_OR_MANAGE", "Ensinar ou acompanhar alunos"
        SELF_KNOWLEDGE = "SELF_KNOWLEDGE", "Entender meus pontos fortes e dificuldades"
        OTHER = "OTHER", "Outro objetivo"

    class DiagnosticTestChoice(models.TextChoices):
        LATER = "LATER", "Deixar para depois"
        STARTED = "STARTED", "Iniciar agora"

    system_role = models.CharField(
        "papel no sistema",
        max_length=16,
        choices=SystemRole.choices,
        default=SystemRole.MEMBER,
    )
    onboarding_role = models.CharField(
        "perfil informado no onboarding",
        max_length=16,
        choices=OnboardingRole.choices,
        blank=True,
    )
    discovery_source = models.CharField(
        "como conheceu a plataforma",
        max_length=20,
        choices=DiscoverySource.choices,
        blank=True,
    )
    education_level = models.CharField(
        "grau de escolaridade",
        max_length=20,
        choices=EducationLevel.choices,
        blank=True,
    )
    app_goal = models.CharField(
        "objetivo com o aplicativo",
        max_length=24,
        choices=AppGoal.choices,
        blank=True,
    )
    app_goal_details = models.CharField(
        "detalhes do objetivo",
        max_length=240,
        blank=True,
    )
    diagnostic_test_choice = models.CharField(
        "escolha do teste diagnóstico",
        max_length=8,
        choices=DiagnosticTestChoice.choices,
        blank=True,
    )
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def has_completed_onboarding(self) -> bool:
        return self.onboarding_completed_at is not None

    def complete_onboarding(self) -> None:
        self.onboarding_completed_at = timezone.now()

    @property
    def is_manager(self) -> bool:
        return self.system_role == self.SystemRole.MANAGER

    @property
    def is_platform_admin(self) -> bool:
        return self.system_role == self.SystemRole.ADMIN

    @property
    def is_system_admin(self) -> bool:
        return self.system_role == self.SystemRole.SYSADMIN

    @property
    def is_teacher(self) -> bool:
        return (
            self.organization_memberships.filter(is_teacher=True).exists()
            or self.teaching_relationships.filter(status="ACTIVE").exists()
            or self.classroom_memberships.filter(role="TEACHER", status="ACTIVE").exists()
        )

    @property
    def is_student(self) -> bool:
        return (
            self.organization_memberships.filter(is_student=True).exists()
            or self.learning_relationships.filter(status="ACTIVE").exists()
            or self.classroom_memberships.filter(role="STUDENT", status="ACTIVE").exists()
        )
