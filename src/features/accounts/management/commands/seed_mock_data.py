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
    EducationalRelationship,
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
        assistant_teacher = self._upsert_user(
            "demo_professor_aux",
            "Rafael",
            "Santos",
            password,
            onboarding_role=get_user_model().OnboardingRole.TEACHER,
        )
        manager = self._upsert_user(
            "demo_gestor",
            "Camila",
            "Ferreira",
            password,
            manager=True,
            onboarding_role=get_user_model().OnboardingRole.MANAGER,
        )
        guardian = self._upsert_user(
            "demo_responsavel",
            "Paulo",
            "Lima",
            password,
            onboarding_role=get_user_model().OnboardingRole.GUARDIAN,
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
        OrganizationMembership.objects.update_or_create(
            organization=organization,
            user=assistant_teacher,
            defaults={"is_teacher": True, "is_student": False, "added_by": teacher},
        )
        OrganizationMembership.objects.update_or_create(
            organization=organization,
            user=manager,
            defaults={"is_teacher": True, "is_student": True, "added_by": teacher},
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
            ClassroomMembership.objects.update_or_create(
                classroom=classroom,
                user=assistant_teacher,
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
            test_specs = (
                ("Diagnóstico inicial", 10, True),
                ("Revisão bimestral", 20, True),
                ("Projeto interdisciplinar", 30, False),
            )
            for title, max_score, is_published in test_specs:
                ClassroomTest.objects.update_or_create(
                    classroom=classroom,
                    title=title,
                    defaults={
                        "instructions": "Atividade demonstrativa gerada pela carga mock.",
                        "max_score": max_score,
                        "created_by": teacher,
                        "is_published": is_published,
                    },
                )

        ClassroomMembership.objects.update_or_create(
            classroom=classrooms[1],
            user=students[0],
            defaults={
                "role": ClassroomMembership.Role.STUDENT,
                "status": MembershipStatus.PENDING,
                "invited_by": teacher,
            },
        )
        ClassroomMembership.objects.update_or_create(
            classroom=classrooms[2],
            user=students[1],
            defaults={
                "role": ClassroomMembership.Role.STUDENT,
                "status": MembershipStatus.REJECTED,
                "invited_by": teacher,
            },
        )

        preparatory = self._upsert_organization(
            "Curso Preparatório Lumini",
            manager,
            "Contexto demonstrativo para preparação de vestibulares e ENEM.",
        )
        preparatory_members = (
            (manager, True, False),
            (teacher, True, False),
            (assistant_teacher, True, False),
            *((student, False, True) for student in students[:6]),
        )
        for member, is_teacher, is_student in preparatory_members:
            OrganizationMembership.objects.update_or_create(
                organization=preparatory,
                user=member,
                defaults={
                    "is_teacher": is_teacher,
                    "is_student": is_student,
                    "added_by": manager,
                },
            )
        prep_root = self._upsert_group("Preparatório", preparatory, manager)
        prep_enem = self._upsert_group("Turmas ENEM", preparatory, manager, prep_root)
        self._upsert_preparatory_classrooms(
            preparatory,
            prep_enem,
            manager,
            teacher,
            assistant_teacher,
            students,
        )

        self._upsert_relationships(
            teacher,
            assistant_teacher,
            manager,
            students,
        )

        anchor = timezone.now().replace(microsecond=0)
        for student_index, student in enumerate(students):
            for cycle in range(6):
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
                        "created_at": anchor - timedelta(days=(5 - cycle) * 14),
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
            "Turma 8º A — manhã",
            {
                "organization": str(organization.pk),
                "classroom": str(classrooms[0].pk),
                "period": "90",
            },
        )
        self._upsert_saved_analysis(
            teacher,
            "Preparatório ENEM",
            {
                "organization": str(preparatory.pk),
                "group": str(prep_enem.pk),
                "period": "all",
            },
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
                "Dados mock atualizados: perfis demonstrativos, duas instituições, "
                "grupos, turmas, convites, vínculos, avaliações e análises salvas."
            )
        )

    def _upsert_user(
        self,
        username,
        first_name,
        last_name,
        password,
        *,
        manager=False,
        onboarding_role=None,
    ):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=username)
        user.first_name = first_name
        user.last_name = last_name
        user.email = f"{username}@demo.lumini.local"
        user.system_role = User.SystemRole.MANAGER if manager else User.SystemRole.MEMBER
        user.onboarding_role = onboarding_role or (
            User.OnboardingRole.TEACHER if manager else User.OnboardingRole.STUDENT
        )
        user.discovery_source = User.DiscoverySource.SCHOOL
        user.education_level = (
            User.EducationLevel.UNDERGRADUATE
            if user.onboarding_role in {User.OnboardingRole.TEACHER, User.OnboardingRole.MANAGER}
            else User.EducationLevel.HIGH_SCHOOL
        )
        user.app_goal = (
            User.AppGoal.TEACH_OR_MANAGE
            if user.onboarding_role in {User.OnboardingRole.TEACHER, User.OnboardingRole.MANAGER}
            else User.AppGoal.IMPROVE_PERFORMANCE
        )
        user.app_goal_details = "Explorar todas as funcionalidades demonstrativas da plataforma."
        user.diagnostic_test_choice = User.DiagnosticTestChoice.LATER
        user.onboarding_completed_at = user.onboarding_completed_at or timezone.now()
        user.is_active = True
        if not user.check_password(password):
            user.set_password(password)
        user.save()
        return user

    def _upsert_organization(self, name, owner, description):
        organization, _ = Organization.objects.update_or_create(
            name=name,
            owner=owner,
            defaults={"description": description, "is_active": True},
        )
        return organization

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

    def _upsert_preparatory_classrooms(
        self,
        organization,
        group,
        manager,
        teacher,
        assistant_teacher,
        students,
    ) -> None:
        classroom_specs = (
            ("ENEM", "N1", Classroom.Shift.EVENING, students[:3]),
            ("ENEM", "I1", Classroom.Shift.FULL_TIME, students[3:6]),
        )
        for name, letter, shift, classroom_students in classroom_specs:
            classroom, _ = Classroom.objects.update_or_create(
                organization=organization,
                group=group,
                name=name,
                letter=letter,
                defaults={
                    "shift": shift,
                    "description": "Turma preparatória com simulados e acompanhamento contínuo.",
                    "owner": manager,
                    "is_active": True,
                },
            )
            for classroom_teacher in (manager, teacher, assistant_teacher):
                ClassroomMembership.objects.update_or_create(
                    classroom=classroom,
                    user=classroom_teacher,
                    defaults={
                        "role": ClassroomMembership.Role.TEACHER,
                        "status": MembershipStatus.ACTIVE,
                        "invited_by": manager,
                    },
                )
            for student in classroom_students:
                ClassroomMembership.objects.update_or_create(
                    classroom=classroom,
                    user=student,
                    defaults={
                        "role": ClassroomMembership.Role.STUDENT,
                        "status": MembershipStatus.ACTIVE,
                        "invited_by": manager,
                    },
                )
            for title, instructions, max_score, is_published in (
                ("Simulado ENEM", "Simulado completo por áreas do conhecimento.", 100, True),
                ("Redação semanal", "Produção textual com tema contemporâneo.", 100, True),
                ("Revisão de competências", "Rascunho para a próxima revisão guiada.", 20, False),
            ):
                ClassroomTest.objects.update_or_create(
                    classroom=classroom,
                    title=title,
                    defaults={
                        "instructions": instructions,
                        "max_score": max_score,
                        "created_by": manager,
                        "is_published": is_published,
                    },
                )

    def _upsert_relationships(self, teacher, assistant_teacher, manager, students) -> None:
        relationship_specs = (
            (teacher, students[0], teacher, MembershipStatus.ACTIVE),
            (teacher, students[1], students[1], MembershipStatus.PENDING),
            (assistant_teacher, students[2], assistant_teacher, MembershipStatus.REJECTED),
            (manager, students[3], students[3], MembershipStatus.REMOVED),
        )
        for relationship_teacher, student, requested_by, status in relationship_specs:
            EducationalRelationship.objects.update_or_create(
                teacher=relationship_teacher,
                student=student,
                defaults={"requested_by": requested_by, "status": status},
            )

    def _upsert_assessments(self, teacher) -> None:
        assessment_specs = (
            (
                "Matemática",
                "Equações do primeiro grau",
                "problem-solving",
                ("deduction", "application"),
                False,
                ("Permitir calculadora simples", "Questões contextualizadas"),
            ),
            (
                "Ciências",
                "Ecossistemas",
                "comparative-questions",
                ("analysis", "comprehension"),
                False,
                ("Usar situações ambientais locais",),
            ),
            (
                "Português",
                "Classes gramaticais",
                "active-recall",
                ("memorization",),
                True,
                ("Evitar frases ambíguas",),
            ),
            (
                "História",
                "Revolução Industrial",
                "socratic-questioning",
                ("critical-thinking",),
                True,
                ("Relacionar causas e consequências", "Incluir fonte histórica curta"),
            ),
            (
                "Geografia",
                "Urbanização brasileira",
                "comparative-questions",
                ("comprehension", "analysis"),
                False,
                ("Comparar regiões brasileiras",),
            ),
            (
                "Redação",
                "Cidadania digital",
                "scenario-application",
                ("application",),
                True,
                ("Modelo dissertativo-argumentativo", "Máximo de 30 linhas"),
            ),
            (
                "Física",
                "Conservação de energia",
                "spaced-review",
                ("memorization", "application"),
                False,
                ("Distribuir a revisão em três blocos", "Incluir unidades no SI"),
            ),
        )
        for subject, topic, technique_code, type_codes, automatic, observations in assessment_specs:
            technique = AssessmentTechnique.objects.get(code=technique_code)
            types = AssessmentType.objects.filter(code__in=type_codes)
            assessment, _ = Assessment.objects.update_or_create(
                owner=teacher,
                subject=subject,
                topic=topic,
                defaults={
                    "observations": list(observations),
                    "technique": technique,
                    "technique_selected_automatically": automatic,
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
