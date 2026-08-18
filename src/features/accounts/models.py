from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuário extensível da aplicação."""

    class SystemRole(models.TextChoices):
        MEMBER = "MEMBER", "Usuário"
        MANAGER = "MANAGER", "Gestor"
        ADMIN = "ADMIN", "Administrador"
        SYSADMIN = "SYSADMIN", "Administrador de sistema"

    system_role = models.CharField(
        "papel no sistema",
        max_length=16,
        choices=SystemRole.choices,
        default=SystemRole.MEMBER,
    )

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
        return self.teaching_relationships.filter(status="ACTIVE").exists() or self.classroom_memberships.filter(
            role="TEACHER", status="ACTIVE"
        ).exists()

    @property
    def is_student(self) -> bool:
        return self.learning_relationships.filter(status="ACTIVE").exists() or self.classroom_memberships.filter(
            role="STUDENT", status="ACTIVE"
        ).exists()
