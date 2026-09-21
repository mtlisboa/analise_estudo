import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from features.analytics_dashboard.models import SavedAnalysis
from features.analytics_dashboard.services import build_dashboard
from features.assessments.models import Assessment, AssessmentTechnique, AssessmentType
from features.users_manager.models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    ClassroomTest,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)


class Command(BaseCommand):
    help = "Cria ou atualiza o conjunto demonstrativo usado no deploy mock."

    students = (
        ("demo_ana", "Ana", "Lima"),
        ("demo_bruno", "Bruno", "Souza"),
        ("demo_clara", "Clara", "Mendes"),
        ("demo_daniel", "Daniel", "Rocha"),
        ("demo_eduarda", "Eduarda", "Alves"),
        ("demo_felipe", "Felipe", "Costa"),
        ("demo_gabriela", "Gabriela", "Nunes"),
        ("demo_henrique", "Henrique", "Silva"),
        ("demo_isabela", "Isabela", "Freitas"),
        ("demo_joao", "João", "Martins"),
        ("demo_karina", "Karina", "Barbosa"),
        ("demo_lucas", "Lucas", "Ferreira"),
    )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        password = os.getenv("MOCK_USER_PASSWORD")
        if not password:
            raise CommandError(
                "Defina MOCK_USER_PASSWORD antes de carregar os dados mock."
            )
        teacher = self._upsert_user(
            "demo_professor",
            "Marina",
            "Oliveira",
            password,
            manager=True,
        )
        students = [
            self._upsert_user(username, first_name, last_name, password)
            for username, first_name, last_name in self.students
        ]

        organization, _ = Organization.objects.update_or_create(
            name="Colégio Lumini Demo",
            owner=teacher,
            defaults={
                "description": "Instituição demonstrativa com grupos, turmas e dados de desempenho.",
                "is_active": True,
            },
        )
        OrganizationMembership.objects.update_or_create(
            organization=organization,
            user=teacher,
            defaults={"is_teacher": True, "is_student": False, "added_by": teacher},
        )
        for student in students:
            OrganizationMembership.objects.update_or_create(
                organization=organization,
                user=student,
                defaults={"is_teacher": False, "is_student": True, "added_by": teacher},
            )

        basic = self._upsert_group("Educação Básica", organization, teacher)
        middle = self._upsert_group("Ensino Fundamental II", organization, teacher, basic)
        high = self._upsert_group("Ensino Médio", organization, teacher, basic)
        grade_8 = self._upsert_group("8º ano", organization, teacher, middle)
        grade_9 = self._upsert_group("9º ano", organization, teacher, middle)
        grade_1 = self._upsert_group("1ª série", organization, teacher, high)

        classroom_specs = (
            ("8º ano", "A", Classroom.Shift.MORNING, grade_8),
            ("8º ano", "B", Classroom.Shift.AFTERNOON, grade_8),
            ("9º ano", "A", Classroom.Shift.MORNING, grade_9),
            ("1ª série", "A", Classroom.Shift.MORNING, grade_1),
        )
        classrooms = []
        for index, (name, letter, shift, group) in enumerate(classroom_specs):
            classroom, _ = Classroom.objects.update_or_create(
                organization=organization,
                group=group,
                name=name,
                letter=letter,
                defaults={
                    "shift": shift,
                    "description": "Turma demonstrativa para visualização de indicadores.",
                    "owner": teacher,
                    "is_active": True,
                },
            )
            classrooms.append(classroom)
            ClassroomMembership.objects.update_or_create(
                classroom=classroom,
                user=teacher,
                defaults={
                    "role": ClassroomMembership.Role.TEACHER,
                    "status": MembershipStatus.ACTIVE,
                    "invited_by": teacher,
                },
            )
            for student in students[index * 3 : index * 3 + 3]:
                ClassroomMembership.objects.update_or_create(
                    classroom=classroom,
                    user=student,
                    defaults={
                        "role": ClassroomMembership.Role.STUDENT,
                        "status": MembershipStatus.ACTIVE,
                        "invited_by": teacher,
                    },
                )
            for test_index, title in enumerate(("Diagnóstico inicial", "Revisão bimestral")):
                ClassroomTest.objects.update_or_create(
                    classroom=classroom,
                    title=title,
                    defaults={
                        "instructions": "Atividade demonstrativa gerada pela carga mock.",
                        "max_score": 10 + test_index * 10,
                        "created_by": teacher,
                        "is_published": True,
                    },
                )

        anchor = timezone.now().replace(microsecond=0)
        for student_index, student in enumerate(students):
            for cycle in range(4):
                focus = 2 + ((student_index + cycle) % 4)
                organization_score = 2 + ((student_index * 2 + cycle) % 4)
                comprehension = 2 + ((student_index + cycle * 2) % 4)
                motivation = 2 + ((student_index * 3 + cycle) % 4)
                SelfAssessment.objects.update_or_create(
                    user=student,
                    notes=f"[MOCK] acompanhamento {cycle + 1}",
                    defaults={
                        "focus": min(focus, 5),
                        "organization": min(organization_score, 5),
                        "comprehension": min(comprehension, 5),
                        "motivation": min(motivation, 5),
                        "created_at": anchor - timedelta(days=(3 - cycle) * 14),
                    },
                )

        self._upsert_assessments(teacher)
        self._upsert_saved_analysis(
            teacher,
            "Panorama geral demonstrativo",
            {"organization": str(organization.pk), "period": "all"},
        )
        self._upsert_saved_analysis(
            teacher,
            "Ensino Fundamental II",
            {
                "organization": str(organization.pk),
                "group": str(middle.pk),
                "period": "all",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Dados mock atualizados: demo_professor e 12 alunos, "
                "com grupos, turmas, avaliações e análises salvas."
            )
        )

    def _upsert_user(self, username, first_name, last_name, password, *, manager=False):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=username)
        user.first_name = first_name
        user.last_name = last_name
        user.email = f"{username}@demo.lumini.local"
        user.system_role = User.SystemRole.MANAGER if manager else User.SystemRole.MEMBER
        user.onboarding_role = (
            User.OnboardingRole.TEACHER if manager else User.OnboardingRole.STUDENT
        )
        user.education_level = User.EducationLevel.HIGH_SCHOOL
        user.app_goal = (
            User.AppGoal.TEACH_OR_MANAGE if manager else User.AppGoal.IMPROVE_PERFORMANCE
        )
        user.onboarding_completed_at = user.onboarding_completed_at or timezone.now()
        user.is_active = True
        if not user.check_password(password):
            user.set_password(password)
        user.save()
        return user

    def _upsert_group(self, name, organization, teacher, parent=None):
        group, _ = ClassroomGroup.objects.update_or_create(
            organization=organization,
            name=name,
            defaults={
                "description": "Grupo demonstrativo da estrutura acadêmica.",
                "parent": parent,
                "created_by": teacher,
                "is_active": True,
            },
        )
        return group

    def _upsert_assessments(self, teacher) -> None:
        technique = AssessmentTechnique.objects.get(code="problem-solving")
        types = AssessmentType.objects.filter(code__in=("deduction", "application", "analysis"))
        subjects = (
            ("Matemática", "Equações do primeiro grau"),
            ("Ciências", "Ecossistemas"),
        )
        for subject, topic in subjects:
            assessment, _ = Assessment.objects.update_or_create(
                owner=teacher,
                subject=subject,
                topic=topic,
                defaults={
                    "observations": ["Dados demonstrativos", "Questões contextualizadas"],
                    "technique": technique,
                    "technique_selected_automatically": False,
                },
            )
            assessment.assessment_types.set(types)

    def _upsert_saved_analysis(self, teacher, title, params) -> None:
        context = build_dashboard(teacher, params)
        SavedAnalysis.objects.update_or_create(
            created_by=teacher,
            title=title,
            defaults={
                "scope_title": context["scope_title"],
                "period_label": context["analytics_payload"]["periodLabel"],
                "filters": context["filters"],
                "snapshot": {
                    "metrics": context["metrics"],
                    "ranking": context["ranking"],
                    "analytics_payload": context["analytics_payload"],
                },
            },
        )
