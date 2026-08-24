from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.users_manager.models import (
    Classroom,
    ClassroomMembership,
    ClassroomTest,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)

User = get_user_model()


class AnalyticsDashboardTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner", password="safe-password")
        self.teacher = User.objects.create_user(username="teacher", password="safe-password")
        self.student = User.objects.create_user(
            username="student",
            first_name="Ana",
            last_name="Lima",
            password="safe-password",
        )
        self.peer = User.objects.create_user(username="peer", password="safe-password")
        self.organization = Organization.objects.create(name="Escola Lumini", owner=self.owner)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            is_teacher=True,
            added_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.teacher,
            is_teacher=True,
            added_by=self.owner,
        )
        for student in (self.student, self.peer):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=student,
                is_student=True,
                added_by=self.owner,
            )
        self.classroom = Classroom.objects.create(
            name="Cálculo I",
            organization=self.organization,
            owner=self.teacher,
        )
        ClassroomMembership.objects.create(
            classroom=self.classroom,
            user=self.teacher,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=self.owner,
        )
        for student in (self.student, self.peer):
            ClassroomMembership.objects.create(
                classroom=self.classroom,
                user=student,
                role=ClassroomMembership.Role.STUDENT,
                status=MembershipStatus.ACTIVE,
                invited_by=self.teacher,
            )
        ClassroomTest.objects.create(
            classroom=self.classroom,
            title="Diagnóstico",
            created_by=self.teacher,
        )
        SelfAssessment.objects.create(
            user=self.student,
            focus=4,
            organization=3,
            comprehension=5,
            motivation=4,
        )
        SelfAssessment.objects.create(
            user=self.peer,
            focus=2,
            organization=2,
            comprehension=3,
            motivation=2,
        )
        self.url = reverse("analytics-dashboard:dashboard")

    def test_dashboard_requires_authentication(self) -> None:
        response = self.client.get(self.url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={self.url}')

    def test_owner_sees_organization_classroom_and_student_metrics(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["metrics"]["organizations"], 1)
        self.assertEqual(response.context["metrics"]["classrooms"], 1)
        self.assertEqual(response.context["metrics"]["students"], 2)
        self.assertEqual(response.context["metrics"]["tests"], 1)
        self.assertEqual(len(response.context["analytics_payload"]["scatter3d"]["names"]), 2)
        self.assertContains(response, 'id="scatter-2d-chart"')
        self.assertContains(response, 'id="scatter-3d-chart"')
        self.assertContains(response, 'id="heatmap-chart"')

    def test_student_only_sees_their_own_academic_data(self) -> None:
        self.client.force_login(self.student)
        response = self.client.get(self.url)

        payload = response.context["analytics_payload"]
        self.assertEqual(response.context["metrics"]["students"], 1)
        self.assertEqual(payload["scatter2d"]["names"], ["Ana Lima"])
        self.assertNotContains(response, "peer")

    def test_teacher_can_filter_a_specific_student(self) -> None:
        self.client.force_login(self.teacher)
        response = self.client.get(
            self.url,
            {"organization": self.organization.pk, "student": self.student.pk, "period": "all"},
        )

        self.assertEqual(response.context["scope_title"], "Ana Lima")
        self.assertEqual(response.context["metrics"]["students"], 1)
        self.assertEqual(response.context["analytics_payload"]["scatter2d"]["names"], ["Ana Lima"])

    def test_invalid_filters_are_ignored_without_exposing_data(self) -> None:
        outsider = User.objects.create_user(username="outsider", password="safe-password")
        outside_organization = Organization.objects.create(name="Externa", owner=outsider)
        self.client.force_login(self.student)

        response = self.client.get(
            self.url,
            {"organization": outside_organization.pk, "student": self.peer.pk, "period": "invalid"},
        )

        self.assertIsNone(response.context["filters"]["organization"])
        self.assertIsNone(response.context["filters"]["student"])
        self.assertEqual(response.context["filters"]["period"], "90")
        self.assertEqual(response.context["analytics_payload"]["scatter2d"]["names"], ["Ana Lima"])
