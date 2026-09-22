import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from features.analytics_dashboard.models import SavedAnalysis
from features.analytics_dashboard.services import build_dashboard
from features.assessments.models import (
    Assessment,
    AssessmentTechnique,
    AssessmentType,
    Question,
)
from features.users_manager.models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    ClassroomTest,
    EducationalRelationship,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    School,
    SchoolApplication,
    SchoolVerificationDocument,
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
        ("demo_maria", "Maria", "Araújo"),
        ("demo_nicolas", "Nicolas", "Cardoso"),
        ("demo_olivia", "Olívia", "Monteiro"),
        ("demo_pedro", "Pedro", "Ribeiro"),
        ("demo_quiteria", "Quitéria", "Moura"),
        ("demo_renato", "Renato", "Cavalcante"),
        ("demo_sophia", "Sophia", "Teixeira"),
        ("demo_thiago", "Thiago", "Correia"),
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
        sysadmin = get_user_model().objects.filter(
            system_role=get_user_model().SystemRole.SYSADMIN
        ).first()
        if not sysadmin:
            sysadmin = get_user_model().objects.create(
                username="mock_school_reviewer",
                system_role=get_user_model().SystemRole.SYSADMIN,
                is_staff=True,
                is_active=True,
            )
            sysadmin.set_unusable_password()
            sysadmin.save(update_fields=("password",))
        school, _ = School.objects.update_or_create(
            organization=organization,
            defaults={
                "legal_name": "Colégio Lumini Demonstração Ltda.",
                "display_name": "Colégio Lumini Demo",
                "school_type": SchoolApplication.SchoolType.PRIVATE,
                "cnpj": "10.000.000/0001-10",
                "inep_code": "26000010",
                "address": "Avenida da Aprendizagem, 100",
                "city": "Recife",
                "state": "PE",
                "approved_by": sysadmin,
            },
        )
        approved_application, _ = SchoolApplication.objects.update_or_create(
            requester=teacher,
            cnpj="10.000.000/0001-10",
            defaults={
                "legal_name": school.legal_name,
                "display_name": school.display_name,
                "school_type": school.school_type,
                "inep_code": school.inep_code,
                "address": school.address,
                "city": school.city,
                "state": school.state,
                "status": SchoolApplication.Status.APPROVED,
                "review_notes": "Documentação demonstrativa aprovada.",
                "reviewed_by": sysadmin,
                "reviewed_at": school.approved_at,
                "approved_school": school,
            },
        )
        pending_application, _ = SchoolApplication.objects.update_or_create(
            requester=manager,
            cnpj="20.000.000/0001-20",
            defaults={
                "legal_name": "Escola Horizonte Público",
                "display_name": "Escola Horizonte",
                "school_type": SchoolApplication.SchoolType.PUBLIC,
                "inep_code": "26000020",
                "address": "Rua das Descobertas, 25",
                "city": "Olinda",
                "state": "PE",
                "status": SchoolApplication.Status.PENDING,
                "review_notes": "",
                "reviewed_by": None,
                "reviewed_at": None,
                "approved_school": None,
            },
        )
        rejected_application, _ = SchoolApplication.objects.update_or_create(
            requester=manager,
            cnpj="30.000.000/0001-30",
            defaults={
                "legal_name": "Instituto Exemplo Privado",
                "display_name": "Instituto Exemplo",
                "school_type": SchoolApplication.SchoolType.PRIVATE,
                "inep_code": "26000030",
                "address": "Rua da Amostra, 30",
                "city": "Jaboatão dos Guararapes",
                "state": "PE",
                "status": SchoolApplication.Status.REJECTED,
                "review_notes": "Documento demonstrativo ilegível; solicitar novo envio.",
                "reviewed_by": sysadmin,
                "reviewed_at": timezone.now(),
                "approved_school": None,
            },
        )
        for application in (approved_application, pending_application, rejected_application):
            if not application.documents.exists():
                document = SchoolVerificationDocument(
                    application=application,
                    original_name="comprovante-mock.pdf",
                )
                document.file.save(
                    f"comprovante-{application.pk}.pdf",
                    ContentFile("Documento comprobatório demonstrativo da Lumini.".encode()),
                    save=True,
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
        grade_8_regular = self._upsert_group(
            "8º ano · Ensino regular", organization, teacher, grade_8
        )
        grade_8_support = self._upsert_group(
            "8º ano · Reforço e projetos", organization, teacher, grade_8
        )
        grade_9_regular = self._upsert_group(
            "9º ano · Ensino regular", organization, teacher, grade_9
        )
        grade_1_general = self._upsert_group(
            "1ª série · Formação geral", organization, teacher, grade_1
        )
        grade_1_exacts = self._upsert_group(
            "1ª série · Itinerário de Exatas", organization, teacher, grade_1
        )

        classroom_specs = (
            ("8º ano", "A", Classroom.Shift.MORNING, grade_8_regular),
            ("8º ano", "B", Classroom.Shift.AFTERNOON, grade_8_regular),
            ("9º ano", "A", Classroom.Shift.MORNING, grade_9_regular),
            ("1ª série", "A", Classroom.Shift.MORNING, grade_1_general),
        )
        classrooms = []
        for index, (name, letter, shift, group) in enumerate(classroom_specs):
            classroom, _ = Classroom.objects.update_or_create(
                organization=organization,
                name=name,
                letter=letter,
                defaults={
                    "group": group,
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

        self._upsert_classroom_with_content(
            organization=organization,
            group=grade_8_support,
            name="Laboratório de aprendizagem",
            letter="R1",
            shift=Classroom.Shift.EVENING,
            owner=teacher,
            teachers=(teacher, assistant_teacher),
            students=students[12:16],
            invited_by=teacher,
            description="Reforço interdisciplinar e desenvolvimento de projetos.",
        )
        self._upsert_classroom_with_content(
            organization=organization,
            group=grade_1_exacts,
            name="Itinerário de Ciências Exatas",
            letter="EX1",
            shift=Classroom.Shift.FULL_TIME,
            owner=teacher,
            teachers=(teacher, assistant_teacher),
            students=students[16:20],
            invited_by=teacher,
            description="Aprofundamento em matemática, física, tecnologia e investigação.",
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
            *((student, False, True) for student in students[:12]),
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
            prep_root,
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
            "Reforço do 8º ano",
            {
                "organization": str(organization.pk),
                "group": str(grade_8_support.pk),
                "period": "all",
            },
        )
        self._upsert_saved_analysis(
            teacher,
            "Itinerário de Ciências Exatas",
            {
                "organization": str(organization.pk),
                "group": str(grade_1_exacts.pk),
                "period": "all",
            },
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
                "credenciamento escolar, grupos, turmas, convites, vínculos, "
                "avaliações e análises salvas."
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
        root_group,
        enem_group,
        manager,
        teacher,
        assistant_teacher,
        students,
    ) -> None:
        enem_extended = self._upsert_group(
            "ENEM · Extensivo", organization, manager, enem_group
        )
        enem_intensive = self._upsert_group(
            "ENEM · Intensivo", organization, manager, enem_group
        )
        ssa_group = self._upsert_group("Turmas SSA", organization, manager, root_group)
        ssa_cycle = self._upsert_group(
            "SSA · Ciclo seriado", organization, manager, ssa_group
        )
        classroom_specs = (
            ("ENEM", "N1", Classroom.Shift.EVENING, enem_extended, students[:3]),
            ("ENEM", "I1", Classroom.Shift.FULL_TIME, enem_intensive, students[3:6]),
            ("SSA 1", "S1", Classroom.Shift.AFTERNOON, ssa_cycle, students[6:9]),
            ("SSA 2", "S2", Classroom.Shift.MORNING, ssa_cycle, students[9:12]),
        )
        for name, letter, shift, group, classroom_students in classroom_specs:
            classroom, _ = Classroom.objects.update_or_create(
                organization=organization,
                name=name,
                letter=letter,
                defaults={
                    "group": group,
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

    def _upsert_classroom_with_content(
        self,
        *,
        organization,
        group,
        name,
        letter,
        shift,
        owner,
        teachers,
        students,
        invited_by,
        description,
    ) -> Classroom:
        classroom, _ = Classroom.objects.update_or_create(
            organization=organization,
            name=name,
            letter=letter,
            defaults={
                "group": group,
                "shift": shift,
                "description": description,
                "owner": owner,
                "is_active": True,
            },
        )
        for classroom_teacher in teachers:
            ClassroomMembership.objects.update_or_create(
                classroom=classroom,
                user=classroom_teacher,
                defaults={
                    "role": ClassroomMembership.Role.TEACHER,
                    "status": MembershipStatus.ACTIVE,
                    "invited_by": invited_by,
                },
            )
        for student in students:
            ClassroomMembership.objects.update_or_create(
                classroom=classroom,
                user=student,
                defaults={
                    "role": ClassroomMembership.Role.STUDENT,
                    "status": MembershipStatus.ACTIVE,
                    "invited_by": invited_by,
                },
            )
        for title, max_score, is_published in (
            ("Diagnóstico da trilha", 10, True),
            ("Projeto aplicado", 30, True),
            ("Plano de acompanhamento", 20, False),
        ):
            ClassroomTest.objects.update_or_create(
                classroom=classroom,
                title=title,
                defaults={
                    "instructions": "Atividade demonstrativa da trilha de aprendizagem.",
                    "max_score": max_score,
                    "created_by": owner,
                    "is_published": is_published,
                },
            )
        return classroom

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
            question_specs = (
                (
                    1,
                    Question.Type.MULTIPLE_CHOICE,
                    f"Sobre {topic}, qual alternativa apresenta a aplicação mais adequada do conteúdo?",
                    [
                        "Aplicar o conceito ao contexto apresentado",
                        "Ignorar os dados do enunciado",
                        "Usar apenas memorização sem justificativa",
                        "Substituir o conceito por uma opinião pessoal",
                    ],
                    "Aplicar o conceito ao contexto apresentado",
                    "A resposta correta relaciona o conceito estudado à situação proposta.",
                    2,
                ),
                (
                    2,
                    Question.Type.OPEN_ENDED,
                    f"Explique, com suas palavras, os principais conceitos de {topic}.",
                    [],
                    "A resposta deve apresentar os conceitos centrais e relacioná-los de forma coerente.",
                    "Considere domínio conceitual, clareza e capacidade de relacionar ideias.",
                    3,
                ),
            )
            for (
                order,
                question_type,
                statement,
                options,
                answer,
                explanation,
                points,
            ) in question_specs:
                Question.objects.update_or_create(
                    assessment=assessment,
                    order=order,
                    defaults={
                        "question_type": question_type,
                        "statement": statement,
                        "options": options,
                        "correct_answer": answer,
                        "explanation": explanation,
                        "points": points,
                    },
                )

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
