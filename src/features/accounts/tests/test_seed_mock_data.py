from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from features.accounts.models import User
from features.analytics_dashboard.models import SavedAnalysis
from features.assessments.models import Assessment
from features.users_manager.models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    ClassroomTest,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)


class SeedMockDataCommandTests(TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_requires_mock_user_password(self) -> None:
        with self.assertRaisesMessage(CommandError, "MOCK_USER_PASSWORD"):
            call_command("seed_mock_data", verbosity=0)

    @patch.dict("os.environ", {"MOCK_USER_PASSWORD": "senha-mock-segura"}, clear=True)
    def test_creates_complete_idempotent_demo_dataset(self) -> None:
        call_command("seed_mock_data", verbosity=0)
        call_command("seed_mock_data", verbosity=0)

        teacher = User.objects.get(username="demo_professor")
        organization = Organization.objects.get(name="Colégio Lumini Demo", owner=teacher)

        self.assertTrue(teacher.check_password("senha-mock-segura"))
        self.assertEqual(User.objects.filter(username__startswith="demo_").count(), 13)
        self.assertEqual(Organization.objects.filter(owner=teacher).count(), 1)
        self.assertEqual(
            OrganizationMembership.objects.filter(organization=organization).count(),
            13,
        )
        self.assertEqual(ClassroomGroup.objects.filter(organization=organization).count(), 6)
        self.assertEqual(Classroom.objects.filter(organization=organization).count(), 4)
        self.assertEqual(
            ClassroomMembership.objects.filter(classroom__organization=organization).count(),
            16,
        )
        self.assertEqual(
            ClassroomTest.objects.filter(classroom__organization=organization).count(),
            8,
        )
        self.assertEqual(
            SelfAssessment.objects.filter(
                user__username__startswith="demo_",
                notes__startswith="[MOCK]",
            ).count(),
            48,
        )
        self.assertEqual(Assessment.objects.filter(owner=teacher).count(), 2)
        self.assertEqual(SavedAnalysis.objects.filter(created_by=teacher).count(), 2)

        middle = ClassroomGroup.objects.get(
            organization=organization,
            name="Ensino Fundamental II",
        )
        grade_8 = ClassroomGroup.objects.get(organization=organization, name="8º ano")
        self.assertEqual(middle.parent.name, "Educação Básica")
        self.assertEqual(grade_8.parent, middle)

        saved_group_analysis = SavedAnalysis.objects.get(
            created_by=teacher,
            title="Ensino Fundamental II",
        )
        self.assertEqual(saved_group_analysis.filters["group"], middle.pk)
        self.assertEqual(
            saved_group_analysis.snapshot["metrics"]["students"],
            9,
        )
