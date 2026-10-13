import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from features.accounts.models import User
from features.analytics_dashboard.models import SavedAnalysis
from features.assessments.models import (
    Assessment,
    AssessmentTechnique,
    AssessmentType,
    Question,
    QuestionBankItem,
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


class SeedMockDataCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        cls.media_directory.cleanup()
        super().tearDownClass()

    @patch.dict("os.environ", {}, clear=True)
    def test_requires_mock_user_password(self) -> None:
        with self.assertRaisesMessage(CommandError, "MOCK_PASSWORD"):
            call_command("seed_mock_data", verbosity=0)

    @patch.dict("os.environ", {"MOCK_PASSWORD": "senha-mock-segura"}, clear=True)
    def test_creates_complete_idempotent_demo_dataset(self) -> None:
        from contexts.institutions.planning.models import Period, Offer, Student, Slot, Teacher, Requirement, Lesson
        from contexts.institutions.coursework.models import Publication
        from contexts.institutions.communication.models import Conversation, Message
        from contexts.institutions.family.models import FamilyRequest, RequestMessage, SchoolEvent
        from features.paper_exams.models import ExamRun, AnswerSheet, ImportBatch, SheetResult
        from features.users_manager.models import ClassroomNotice
        from features.assessments.models import QuestionImage
        from features.notifications.models import Notification
        mock_models = (Period, Offer, Student, Slot, Teacher, Requirement, Lesson, Publication,
            Conversation, Message, FamilyRequest, RequestMessage, SchoolEvent, ExamRun,
            AnswerSheet, ImportBatch, SheetResult, ClassroomNotice, QuestionImage, Notification)
        call_command("seed_mock_data", verbosity=0)
        identities = {model: set(model.objects.values_list('pk', flat=True)) for model in mock_models}
        call_command("seed_mock_data", verbosity=0)
        for model in mock_models:
            self.assertTrue(identities[model], model.__name__)
            self.assertEqual(identities[model], set(model.objects.values_list('pk', flat=True)), model.__name__)
        from contexts.institutions.planning.services import pending_issues, validate_existing
        period = Period.objects.get()
        validate_existing(period)
        self.assertEqual(pending_issues(period), [])
        self.assertEqual(Offer.objects.count(), 6)
        self.assertEqual(Publication.objects.filter(is_published=True).count(), 24)
        self.assertEqual(Publication.objects.filter(is_published=False).count(), 12)
        self.assertTrue(SheetResult.objects.filter(status='graded').exists())
        self.assertTrue(SheetResult.objects.filter(status='review').exists())
        self.assertFalse(Classroom.objects.filter(organization__name='Colégio Lumini Demo', cover_image='').exists())
        from django.urls import reverse
        for username, path in (('demo_aluno', 'institutions:aluno'), ('demo_professor', 'institutions:professor'),
                ('demo_responsavel', 'family:index'), ('demo_gestor', 'institutions:gestor'),
                ('demo_admin', 'institutions:gestor'), ('demo_operador', 'institutions:operador')):
            self.client.force_login(User.objects.get(username=username))
            self.assertEqual(self.client.get(reverse(path)).status_code, 200)


        teacher = User.objects.get(username="demo_professor")
        organization = Organization.objects.get(name="Colégio Lumini Demo", owner__username="demo_admin")

        from contexts.institutions.family.models import GuardianLink
        self.assertEqual(GuardianLink.objects.filter(guardian__user__username='demo_responsavel',
            student__user__username='demo_aluno', is_active=True).count(), 1)

        self.assertTrue(teacher.check_password("senha-mock-segura"))
        self.assertEqual(User.objects.filter(username__startswith="demo_").count(), 27)
        self.assertEqual(Organization.objects.filter(owner__username="demo_admin").count(), 1)
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(
            OrganizationMembership.objects.filter(organization=organization).count(),
            23,
        )
        self.assertEqual(ClassroomGroup.objects.filter(organization=organization).count(), 11)
        self.assertEqual(ClassroomGroup.objects.count(), 17)
        self.assertEqual(Classroom.objects.filter(organization=organization).count(), 6)
        self.assertEqual(Classroom.objects.count(), 10)
        self.assertEqual(
            ClassroomMembership.objects.filter(classroom__organization=organization).count(),
            35,
        )
        self.assertEqual(ClassroomMembership.objects.count(), 59)
        self.assertEqual(
            ClassroomTest.objects.filter(classroom__organization=organization).count(),
            18,
        )
        self.assertEqual(ClassroomTest.objects.count(), 30)
        self.assertEqual(ClassroomTest.objects.filter(is_published=False).count(), 10)
        self.assertEqual(
            SelfAssessment.objects.filter(
                user__username__startswith="demo_",
                notes__startswith="[MOCK]",
            ).count(),
            126,
        )
        self.assertEqual(Assessment.objects.filter(owner=teacher).count(), 8)
        self.assertEqual(Question.objects.filter(assessment__owner=teacher).count(), 19)
        self.assertEqual(QuestionBankItem.objects.filter(owner=teacher).count(), 14)
        self.assertEqual(SavedAnalysis.objects.filter(created_by=teacher).count(), 6)
        self.assertEqual(EducationalRelationship.objects.count(), 4)
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(SchoolApplication.objects.count(), 3)
        self.assertEqual(SchoolVerificationDocument.objects.count(), 3)
        self.assertEqual(
            set(SchoolApplication.objects.values_list("status", flat=True)),
            set(SchoolApplication.Status.values),
        )

        self.assertEqual(
            set(Classroom.objects.values_list("shift", flat=True)),
            set(Classroom.Shift.values),
        )
        self.assertEqual(
            set(
                AssessmentTechnique.objects.filter(assessments__owner=teacher)
                .values_list("code", flat=True)
                .distinct()
            ),
            set(AssessmentTechnique.objects.values_list("code", flat=True)),
        )
        self.assertEqual(
            set(
                AssessmentType.objects.filter(assessments__owner=teacher)
                .values_list("code", flat=True)
                .distinct()
            ),
            set(AssessmentType.objects.values_list("code", flat=True)),
        )
        self.assertEqual(
            set(EducationalRelationship.objects.values_list("status", flat=True)),
            {
                MembershipStatus.ACTIVE,
                MembershipStatus.PENDING,
                MembershipStatus.REJECTED,
                MembershipStatus.REMOVED,
            },
        )
        self.assertTrue(
            ClassroomMembership.objects.filter(status=MembershipStatus.PENDING).exists()
        )
        self.assertTrue(
            ClassroomMembership.objects.filter(status=MembershipStatus.REJECTED).exists()
        )

        middle = ClassroomGroup.objects.get(
            organization=organization,
            name="Ensino Fundamental II",
        )
        grade_8 = ClassroomGroup.objects.get(organization=organization, name="8º ano")
        grade_8_support = ClassroomGroup.objects.get(
            organization=organization,
            name="8º ano · Reforço e projetos",
        )
        self.assertEqual(middle.parent.name, "Educação Básica")
        self.assertEqual(grade_8.parent, middle)
        self.assertEqual(grade_8_support.parent, grade_8)
        self.assertTrue(grade_8_support.classrooms.filter(letter="R1").exists())

        ssa_cycle = ClassroomGroup.objects.get(name="SSA · Ciclo seriado")
        self.assertEqual(ssa_cycle.parent.name, "Turmas SSA")
        self.assertEqual(ssa_cycle.parent.parent.name, "Preparatório")
        self.assertEqual(ssa_cycle.classrooms.count(), 2)

        saved_group_analysis = SavedAnalysis.objects.get(
            created_by=teacher,
            title="Ensino Fundamental II",
        )
        self.assertEqual(saved_group_analysis.filters["group"], middle.pk)
        self.assertEqual(
            saved_group_analysis.snapshot["metrics"]["students"],
            14,
        )

    @patch.dict('os.environ', {'MOCK_PASSWORD': 'demo-test-secret-123', 'DEPLOY_MODE': 'MOCK'}, clear=True)
    def test_institutional_demo_logins_roles_and_password_rotation(self):
        from django.contrib.auth import authenticate
        from django.urls import reverse
        from features.accounts.demo import DEMO_ROLES
        from features.users_manager.models import InstitutionalAccount
        call_command('seed_mock_data', verbosity=0)
        routes = {'ADMIN': 'gestor', 'MANAGER': 'gestor', 'OPERATOR': 'operador',
                  'TEACHER': 'professor', 'STUDENT': 'aluno', 'GUARDIAN': 'responsavel'}
        for username, role in DEMO_ROLES.items():
            user = authenticate(username=username, password='demo-test-secret-123')
            self.assertIsNotNone(user, username)
            identity = InstitutionalAccount.objects.get(user=user)
            self.assertEqual(identity.role, role)
            self.assertEqual(user.system_role, User.SystemRole.MEMBER)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertFalse(user.must_change_password)
            self.client.force_login(user)
            self.assertRedirects(self.client.get(reverse('institutions:index')),
                                 reverse('family:index') if role == 'GUARDIAN' else reverse('institutions:' + routes[role]))
        self.assertEqual(InstitutionalAccount.objects.count(), 27)
        admin = User.objects.get(username='demo_admin')
        self.assertEqual(Organization.objects.get(name='Colégio Lumini Demo').owner, admin)
        from features.accounts.institutional import can_provision
        self.assertTrue(can_provision(admin, admin.institutional_account.organization))
        for username in ('demo_gestor', 'demo_operador'):
            user = User.objects.get(username=username)
            self.assertFalse(can_provision(user, user.institutional_account.organization))
            self.assertFalse(OrganizationMembership.objects.filter(
                organization=user.institutional_account.organization, user=user).exists())
        with patch.dict('os.environ', {'DEPLOY_MODE': ''}):
            self.assertIsNone(authenticate(username='demo_admin', password='demo-test-secret-123'))
            self.assertIsNotNone(authenticate(username=admin.email, password='demo-test-secret-123'))
        ids = dict(InstitutionalAccount.objects.values_list('registration', 'pk'))
        with patch.dict('os.environ', {'MOCK_PASSWORD': 'rotated-demo-secret-456'}):
            call_command('seed_mock_data', verbosity=0)
        self.assertEqual(ids, dict(InstitutionalAccount.objects.values_list('registration', 'pk')))
        for username in DEMO_ROLES:
            self.assertIsNone(authenticate(username=username, password='demo-test-secret-123'))
            self.assertIsNotNone(authenticate(username=username, password='rotated-demo-secret-456'))

    @patch.dict('os.environ', {'MOCK_PASSWORD': '   ', 'MOCK_USER_PASSWORD': 'ignored'}, clear=True)
    def test_blank_password_has_no_fallback(self):
        with self.assertRaisesMessage(CommandError, 'MOCK_PASSWORD'):
            call_command('seed_mock_data', verbosity=0)
        self.assertFalse(User.objects.filter(username__startswith='demo_').exists())

    @patch.dict('os.environ', {'MOCK_PASSWORD': 'demo-test-secret-123'}, clear=True)
    def test_existing_non_demo_account_is_not_overwritten(self):
        user = User.objects.create_user(username='demo_admin', email='admin@real-school.example', password='original')
        with self.assertRaisesMessage(CommandError, 'não demonstrativa'):
            call_command('seed_mock_data', verbosity=0)
        user.refresh_from_db()
        self.assertTrue(user.check_password('original'))
        self.assertEqual(user.email, 'admin@real-school.example')
