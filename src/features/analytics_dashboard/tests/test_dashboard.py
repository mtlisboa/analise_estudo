from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.analytics_dashboard.models import SavedAnalysis
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
        self.classroom_group = ClassroomGroup.objects.create(
            name="Ensino médio",
            organization=self.organization,
            created_by=self.teacher,
        )
        self.classroom = Classroom.objects.create(
            name="Cálculo I",
            organization=self.organization,
            group=self.classroom_group,
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
        self.generate_url = reverse("analytics-dashboard:generate")

    def generate_analysis(self, user, **overrides) -> SavedAnalysis:
        self.client.force_login(user)
        data = {
            "title": "Análise de setembro",
            "organization": str(self.organization.pk),
            "classroom": str(self.classroom.pk),
            "student": "",
            "period": "all",
        }
        data.update(overrides)
        response = self.client.post(self.generate_url, data)
        analysis = SavedAnalysis.objects.get(created_by=user)
        self.assertRedirects(
            response,
            reverse("analytics-dashboard:detail", kwargs={"pk": analysis.pk}),
        )
        return analysis

    def test_dashboard_requires_authentication(self) -> None:
        response = self.client.get(self.url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={self.url}')

    def test_index_only_shows_saved_analyses_and_generate_button(self) -> None:
        analysis = self.generate_analysis(self.owner)

        response = self.client.get(self.url)

        self.assertContains(response, analysis.title)
        self.assertContains(response, "Gerar nova análise")
        self.assertNotContains(response, 'id="scatter-2d-chart"')

    def test_owner_generates_and_views_a_persisted_snapshot(self) -> None:
        analysis = self.generate_analysis(self.owner)
        response = self.client.get(
            reverse("analytics-dashboard:detail", kwargs={"pk": analysis.pk})
        )

        self.assertEqual(analysis.snapshot["metrics"]["organizations"], 1)
        self.assertEqual(analysis.snapshot["metrics"]["classrooms"], 1)
        self.assertEqual(analysis.snapshot["metrics"]["students"], 2)
        self.assertEqual(analysis.snapshot["metrics"]["tests"], 1)
        self.assertEqual(len(analysis.snapshot["analytics_payload"]["scatter3d"]["names"]), 2)
        self.assertContains(response, 'id="scatter-2d-chart"')
        self.assertContains(response, 'id="scatter-3d-chart"')
        self.assertContains(response, 'id="heatmap-chart"')

    def test_student_only_sees_their_own_academic_data(self) -> None:
        analysis = self.generate_analysis(self.student)

        payload = analysis.snapshot["analytics_payload"]
        self.assertEqual(analysis.snapshot["metrics"]["students"], 1)
        self.assertEqual(payload["scatter2d"]["names"], ["Ana Lima"])
        self.assertNotIn("peer", str(analysis.snapshot))

    def test_teacher_can_filter_a_specific_student(self) -> None:
        analysis = self.generate_analysis(
            self.teacher,
            student=str(self.student.pk),
        )

        self.assertEqual(analysis.scope_title, "Ana Lima")
        self.assertEqual(analysis.snapshot["metrics"]["students"], 1)
        self.assertEqual(
            analysis.snapshot["analytics_payload"]["scatter2d"]["names"],
            ["Ana Lima"],
        )

    def test_invalid_filters_do_not_create_or_expose_an_analysis(self) -> None:
        outsider = User.objects.create_user(username="outsider", password="safe-password")
        outside_organization = Organization.objects.create(name="Externa", owner=outsider)
        self.client.force_login(self.student)

        response = self.client.post(
            self.generate_url,
            {
                "title": "Indevida",
                "organization": str(outside_organization.pk),
                "classroom": "",
                "student": str(self.peer.pk),
                "period": "invalid",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SavedAnalysis.objects.exists())
        self.assertContains(response, "Faça uma escolha válida")

    def test_user_cannot_view_another_users_saved_analysis(self) -> None:
        analysis = self.generate_analysis(self.owner)
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("analytics-dashboard:detail", kwargs={"pk": analysis.pk})
        )

        self.assertEqual(response.status_code, 404)
