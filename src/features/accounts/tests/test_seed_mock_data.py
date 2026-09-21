from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from features.accounts.models import User
from features.analytics_dashboard.models import SavedAnalysis
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
        self.assertEqual(User.objects.filter(username__startswith="demo_").count(), 24)
        self.assertEqual(Organization.objects.filter(owner=teacher).count(), 1)
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
            34,
        )
        self.assertEqual(ClassroomMembership.objects.count(), 58)
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
            120,
        )
        self.assertEqual(Assessment.objects.filter(owner=teacher).count(), 7)
        self.assertEqual(Question.objects.filter(assessment__owner=teacher).count(), 14)
        self.assertEqual(SavedAnalysis.objects.filter(created_by=teacher).count(), 6)
        self.assertEqual(EducationalRelationship.objects.count(), 4)

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
            13,
        )
