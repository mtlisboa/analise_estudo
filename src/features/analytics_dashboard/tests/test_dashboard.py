from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.analytics_dashboard.models import SavedAnalysis
from features.analytics_dashboard.services import build_dashboard
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
            "action": "save",
            "title": "Análise de setembro",
            "organization": str(self.organization.pk),
            "group": "",
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

    def generate_preview(self, user, **overrides):
        self.client.force_login(user)
        data = {
            "action": "generate",
            "organization": str(self.organization.pk),
            "group": "",
            "classroom": str(self.classroom.pk),
            "student": "",
            "period": "all",
        }
        data.update(overrides)
        return self.client.post(self.generate_url, data)

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
        self.assertContains(response, 'id="classroom-scatter-chart"')
        self.assertContains(response, 'id="classroom-scope-select"')
        self.assertContains(response, 'id="toggle-analysis-chart-size"')
        self.assertNotContains(response, 'id="timeline-chart"')
        self.assertNotContains(response, 'id="classroom-chart"')
        self.assertNotContains(response, 'id="roles-chart"')
        self.assertNotContains(response, 'id="scatter-3d-chart"')
        self.assertNotContains(response, 'id="heatmap-chart"')
        student_snapshot = analysis.snapshot["analytics_payload"]["students"][0]
        self.assertIn("classrooms", student_snapshot)
        self.assertIn("assessments", student_snapshot)
        self.assertEqual(student_snapshot["classrooms"][0]["id"], self.classroom.pk)

    def test_generation_shows_preview_without_saving_automatically(self) -> None:
        response = self.generate_preview(self.owner)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SavedAnalysis.objects.exists())
        self.assertContains(response, "Esta análise ainda não foi salva")
        self.assertContains(response, 'value="save"')
        self.assertContains(response, 'id="classroom-scatter-chart"')

    def test_optional_save_persists_the_selection_from_the_scatter_map(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.post(
            self.generate_url,
            {
                "action": "save",
                "title": "Seleção visual",
                "organization": str(self.organization.pk),
                "group": "",
                "classroom": str(self.classroom.pk),
                "student": "",
                "selected_students": str(self.student.pk),
                "selection_label": "Ana Lima",
                "period": "all",
            },
        )

        analysis = SavedAnalysis.objects.get(created_by=self.owner)
        self.assertRedirects(
            response,
            reverse("analytics-dashboard:detail", kwargs={"pk": analysis.pk}),
        )
        self.assertEqual(analysis.scope_title, "Ana Lima")
        self.assertEqual(analysis.filters["selected_students"], [self.student.pk])
        self.assertEqual(analysis.snapshot["metrics"]["students"], 1)
        self.assertEqual(
            analysis.snapshot["analytics_payload"]["scatter2d"]["names"],
            ["Ana Lima"],
        )

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

    def test_analysis_can_include_a_group_and_its_nested_groups(self) -> None:
        parent_group = ClassroomGroup.objects.create(
            name="Educação básica",
            organization=self.organization,
            created_by=self.teacher,
        )
        self.classroom_group.parent = parent_group
        self.classroom_group.save(update_fields=("parent",))
        excluded_group = ClassroomGroup.objects.create(
            name="Cursos livres",
            organization=self.organization,
            created_by=self.teacher,
        )
        excluded_classroom = Classroom.objects.create(
            name="Robótica",
            organization=self.organization,
            group=excluded_group,
            owner=self.teacher,
        )
        ClassroomMembership.objects.create(
            classroom=excluded_classroom,
            user=self.teacher,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=self.owner,
        )

        analysis = self.generate_analysis(
            self.teacher,
            group=str(parent_group.pk),
            classroom="",
        )

        self.assertEqual(analysis.scope_title, "Educação básica")
        self.assertEqual(analysis.filters["group"], parent_group.pk)
        self.assertEqual(analysis.snapshot["metrics"]["classrooms"], 1)
        self.assertNotIn("Robótica", analysis.snapshot["analytics_payload"]["classrooms"]["labels"])

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

    def test_teacher_analysis_is_limited_to_their_classrooms(self) -> None:
        other_teacher = User.objects.create_user(
            username="other-teacher", password="safe-password"
        )
        other_student = User.objects.create_user(
            username="other-student", password="safe-password"
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=other_teacher,
            is_teacher=True,
            added_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=other_student,
            is_student=True,
            added_by=self.owner,
        )
        other_group = ClassroomGroup.objects.create(
            name="Grupo restrito",
            organization=self.organization,
            created_by=other_teacher,
        )
        other_classroom = Classroom.objects.create(
            name="Turma de outro professor",
            organization=self.organization,
            group=other_group,
            owner=other_teacher,
        )
        ClassroomMembership.objects.create(
            classroom=other_classroom,
            user=other_teacher,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=self.owner,
        )
        ClassroomMembership.objects.create(
            classroom=other_classroom,
            user=other_student,
            role=ClassroomMembership.Role.STUDENT,
            status=MembershipStatus.ACTIVE,
            invited_by=other_teacher,
        )

        context = build_dashboard(self.teacher, {})

        self.assertEqual(context["classrooms"], [self.classroom])
        self.assertNotIn(other_group, context["classroom_groups"])
        self.assertNotIn(other_student, context["students"])
        self.assertEqual(context["metrics"]["classrooms"], 1)
        self.assertEqual(context["metrics"]["students"], 2)

    def test_user_cannot_view_another_users_saved_analysis(self) -> None:
        analysis = self.generate_analysis(self.owner)
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("analytics-dashboard:detail", kwargs={"pk": analysis.pk})
        )

        self.assertEqual(response.status_code, 404)
