from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from features.accounts.models import User
from features.assessments.models import Assessment, AssessmentTechnique, AssessmentType
from features.users_manager.models import (
    Classroom,
    ClassroomMembership,
    ClassroomTest,
    EducationalRelationship,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)


class Command(BaseCommand):
    help = "Provisiona dados idempotentes de demonstração quando DEPLOY_MODE=MOCK."

    def handle(self, *args, **options):
        if not settings.MOCK_MODE:
            self.stdout.write("DEPLOY_MODE não é MOCK; nenhum dado foi criado.")
            return

        with transaction.atomic():
            users = self._seed_users()
            organizations, classrooms = self._seed_learning_context(users)
            self._seed_self_assessments(users)
            self._seed_assessments(users["demo"])
            self._seed_relationships(users)

        self.stdout.write(
            self.style.SUCCESS(
                "Ambiente MOCK pronto: "
                f"{len(users)} usuários, {len(organizations)} organizações e "
                f"{len(classrooms)} turmas. Login: {settings.MOCK_USERNAME}"
            )
        )

    def _seed_users(self):
        profiles = {
            "demo": (settings.MOCK_USERNAME, "Matheus", "Demo", "demo@lumini.local"),
            "teacher": ("professora.demo", "Helena", "Costa", "helena@lumini.local"),
            "student_1": ("ana.demo", "Ana", "Lima", "ana@lumini.local"),
            "student_2": ("bruno.demo", "Bruno", "Silva", "bruno@lumini.local"),
            "student_3": ("carla.demo", "Carla", "Souza", "carla@lumini.local"),
            "student_4": ("diego.demo", "Diego", "Alves", "diego@lumini.local"),
        }
        users = {}
        for key, (username, first_name, last_name, email) in profiles.items():
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "onboarding_role": (
                        User.OnboardingRole.TEACHER
                        if key in {"demo", "teacher"}
                        else User.OnboardingRole.STUDENT
                    ),
                    "discovery_source": User.DiscoverySource.SEARCH,
                    "education_level": User.EducationLevel.HIGH_SCHOOL,
                    "app_goal": User.AppGoal.IMPROVE_PERFORMANCE,
                    "app_goal_details": "Explorar todas as funcionalidades da demonstração.",
                    "diagnostic_test_choice": User.DiagnosticTestChoice.STARTED,
                    "onboarding_completed_at": timezone.now(),
                    "is_active": True,
                },
            )
            user.set_password(settings.MOCK_PASSWORD)
            user.save(update_fields=("password",))
            users[key] = user
        return users

    def _seed_learning_context(self, users):
        demo = users["demo"]
        organization_specs = (
            ("Escola Lumini", "Contexto completo para acompanhar turmas e estudantes."),
            ("Preparatório Horizonte", "Preparação para provas e diagnósticos de aprendizagem."),
        )
        organizations = []
        for name, description in organization_specs:
            organization, _ = Organization.objects.update_or_create(
                name=name,
                owner=demo,
                defaults={"description": description, "is_active": True},
            )
            organizations.append(organization)
            self._membership(organization, demo, demo, teacher=True, student=True)
            self._membership(organization, users["teacher"], demo, teacher=True)
            for key in ("student_1", "student_2", "student_3", "student_4"):
                self._membership(organization, users[key], demo, student=True)

        classroom_specs = (
            (organizations[0], "Matemática — 3º ano", "Álgebra, funções e geometria."),
            (organizations[0], "Ciências da Natureza", "Física, química e biologia integradas."),
            (organizations[1], "Preparação ENEM", "Turma intensiva com simulados semanais."),
        )
        classrooms = []
        students = [users[f"student_{index}"] for index in range(1, 5)]
        for index, (organization, name, description) in enumerate(classroom_specs):
            classroom, _ = Classroom.objects.update_or_create(
                organization=organization,
                name=name,
                defaults={"description": description, "owner": demo, "is_active": True},
            )
            classrooms.append(classroom)
            self._classroom_membership(classroom, demo, demo, ClassroomMembership.Role.TEACHER)
            self._classroom_membership(
                classroom, users["teacher"], demo, ClassroomMembership.Role.TEACHER
            )
            for student in students[index % 2 :]:
                self._classroom_membership(
                    classroom, student, demo, ClassroomMembership.Role.STUDENT
                )
            for test_index, title in enumerate(
                ("Diagnóstico inicial", "Revisão orientada", "Simulado de progresso"), start=1
            ):
                ClassroomTest.objects.update_or_create(
                    classroom=classroom,
                    title=f"{title} {index + 1}",
                    defaults={
                        "instructions": "Responda com atenção e registre o raciocínio utilizado.",
                        "max_score": 10 + test_index * 5,
                        "created_by": demo,
                        "is_published": test_index != 2,
                    },
                )
        return organizations, classrooms

    @staticmethod
    def _membership(organization, user, added_by, *, teacher=False, student=False):
        OrganizationMembership.objects.update_or_create(
            organization=organization,
            user=user,
            defaults={
                "is_teacher": teacher,
                "is_student": student,
                "added_by": added_by,
            },
        )

    @staticmethod
    def _classroom_membership(classroom, user, invited_by, role):
        ClassroomMembership.objects.update_or_create(
            classroom=classroom,
            user=user,
            defaults={
                "role": role,
                "status": MembershipStatus.ACTIVE,
                "invited_by": invited_by,
            },
        )

    def _seed_self_assessments(self, users):
        now = timezone.now()
        patterns = {
            "demo": ((4, 4, 4, 5), (5, 4, 5, 5)),
            "student_1": ((3, 3, 4, 4), (4, 4, 5, 5), (5, 4, 5, 4)),
            "student_2": ((2, 3, 3, 3), (3, 3, 4, 4), (4, 4, 4, 4)),
            "student_3": ((4, 2, 4, 3), (4, 3, 5, 4), (5, 4, 5, 5)),
            "student_4": ((3, 4, 3, 4), (4, 4, 4, 5), (4, 5, 5, 5)),
        }
        for key, records in patterns.items():
            for index, (focus, organization, comprehension, motivation) in enumerate(records):
                created_at = now - timedelta(days=(len(records) - index) * 14)
                assessment, _ = SelfAssessment.objects.update_or_create(
                    user=users[key],
                    notes=f"Registro demonstrativo {index + 1}",
                    defaults={
                        "focus": focus,
                        "organization": organization,
                        "comprehension": comprehension,
                        "motivation": motivation,
                        "created_at": created_at,
                    },
                )
                SelfAssessment.objects.filter(pk=assessment.pk).update(created_at=created_at)

    @staticmethod
    def _seed_assessments(owner):
        types = {
            item.code: item
            for item in AssessmentType.objects.select_related("default_technique")
        }
        techniques = {item.code: item for item in AssessmentTechnique.objects.all()}
        specs = (
            ("MATEMÁTICA", "Funções quadráticas", ["Sem calculadora", "Justificar cada etapa"], ["deduction", "application"], "problem-solving"),
            ("BIOLOGIA", "Genética mendeliana", ["Priorizar interpretação", "Incluir heredogramas"], ["comprehension", "analysis"], "comparative-questions"),
            ("HISTÓRIA", "Brasil República", ["Relacionar causas e consequências"], ["memorization", "critical-thinking"], "active-recall"),
            ("FÍSICA", "Dinâmica e energia", ["Usar situações cotidianas"], ["application", "deduction"], "scenario-application"),
        )
        for subject, topic, observations, type_codes, technique_code in specs:
            assessment, _ = Assessment.objects.update_or_create(
                owner=owner,
                subject=subject,
                topic=topic,
                defaults={
                    "observations": observations,
                    "technique": techniques[technique_code],
                    "technique_selected_automatically": subject == "HISTÓRIA",
                },
            )
            assessment.assessment_types.set(types[code] for code in type_codes)

    @staticmethod
    def _seed_relationships(users):
        EducationalRelationship.objects.update_or_create(
            teacher=users["teacher"],
            student=users["student_1"],
            defaults={
                "requested_by": users["teacher"],
                "status": MembershipStatus.ACTIVE,
            },
        )
