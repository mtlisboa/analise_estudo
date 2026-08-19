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


class UsersManagerTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="matheus",
            email="matheus@example.com",
            password="senha-forte-123",
        )
        self.teacher = User.objects.create_user(
            username="professora",
            email="professora@example.com",
            password="senha-forte-456",
        )
        self.student = User.objects.create_user(
            username="aluno",
            email="aluno@example.com",
            password="senha-forte-789",
        )
        self.client.force_login(self.owner)

    def create_organization(self) -> Organization:
        organization = Organization.objects.create(name="Escola Lumini", owner=self.owner)
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.owner,
            is_teacher=True,
            added_by=self.owner,
        )
        return organization

    def add_member(self, organization, user, *, teacher=False, student=False):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            is_teacher=teacher,
            is_student=student,
            added_by=self.owner,
        )

    def create_classroom(self, organization, owner=None) -> Classroom:
        teacher = owner or self.owner
        classroom = Classroom.objects.create(
            name="Cálculo I",
            organization=organization,
            owner=teacher,
        )
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=teacher,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=teacher,
        )
        return classroom

    def test_manager_dashboard_requires_authentication(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("users-manager:dashboard"))
        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("users-manager:dashboard")}',
        )

    def test_user_can_create_organization_and_becomes_teacher_member(self) -> None:
        response = self.client.post(
            reverse("users-manager:organization-create"),
            {
                "name": "Escola Lumini",
                "description": "Unidade João Pessoa",
                "is_teacher": "on",
            },
        )
        organization = Organization.objects.get(name="Escola Lumini")
        self.assertRedirects(
            response,
            reverse("users-manager:organization-detail", kwargs={"pk": organization.pk}),
        )
        membership = organization.memberships.get(user=self.owner)
        self.assertTrue(membership.is_teacher)
        self.assertFalse(membership.is_student)

    def test_creator_can_join_new_organization_only_as_student(self) -> None:
        response = self.client.post(
            reverse("users-manager:organization-create"),
            {
                "name": "Grupo de estudos",
                "description": "",
                "is_student": "on",
            },
        )

        organization = Organization.objects.get(name="Grupo de estudos")
        membership = organization.memberships.get(user=self.owner)
        self.assertRedirects(
            response,
            reverse("users-manager:organization-detail", kwargs={"pk": organization.pk}),
        )
        self.assertFalse(membership.is_teacher)
        self.assertTrue(membership.is_student)

    def test_owner_can_add_user_with_teacher_and_student_flags(self) -> None:
        organization = self.create_organization()
        response = self.client.post(
            reverse("users-manager:organization-member-add", kwargs={"pk": organization.pk}),
            {"email": self.teacher.email, "is_teacher": "on", "is_student": "on"},
        )
        self.assertRedirects(
            response,
            reverse("users-manager:organization-detail", kwargs={"pk": organization.pk}),
        )
        membership = organization.memberships.get(user=self.teacher)
        self.assertTrue(membership.is_teacher)
        self.assertTrue(membership.is_student)
        self.assertTrue(self.teacher.is_teacher)
        self.assertTrue(self.teacher.is_student)

    def test_member_requires_at_least_one_educational_flag(self) -> None:
        organization = self.create_organization()
        response = self.client.post(
            reverse("users-manager:organization-member-add", kwargs={"pk": organization.pk}),
            {"email": self.student.email},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marque pelo menos um papel")
        self.assertFalse(organization.memberships.filter(user=self.student).exists())

    def test_non_owner_cannot_add_organization_members(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.teacher, teacher=True)
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("users-manager:organization-member-add", kwargs={"pk": organization.pk}),
            {"email": self.student.email, "is_student": "on"},
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_create_classroom_inside_organization(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.teacher, teacher=True)
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("users-manager:classroom-create", kwargs={"organization_pk": organization.pk}),
            {"name": "Cálculo I", "description": "Turma da manhã"},
        )
        classroom = Classroom.objects.get(name="Cálculo I")
        self.assertEqual(classroom.organization, organization)
        self.assertEqual(classroom.owner, self.teacher)
        self.assertRedirects(
            response,
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}),
        )

    def test_student_cannot_create_classroom(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.student, student=True)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("users-manager:classroom-create", kwargs={"organization_pk": organization.pk}),
            {"name": "Turma indevida"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Classroom.objects.filter(name="Turma indevida").exists())

    def test_teacher_adds_organization_student_to_classroom(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.student, student=True)
        classroom = self.create_classroom(organization)
        response = self.client.post(
            reverse("users-manager:classroom-invite", kwargs={"pk": classroom.pk}),
            {"email": self.student.email, "role": ClassroomMembership.Role.STUDENT},
        )
        membership = classroom.memberships.get(user=self.student)
        self.assertRedirects(
            response,
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}),
        )
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)
        self.assertEqual(membership.role, ClassroomMembership.Role.STUDENT)

    def test_user_outside_organization_cannot_join_classroom(self) -> None:
        organization = self.create_organization()
        classroom = self.create_classroom(organization)
        response = self.client.post(
            reverse("users-manager:classroom-invite", kwargs={"pk": classroom.pk}),
            {"email": self.student.email, "role": ClassroomMembership.Role.STUDENT},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adicione o usuário à organização")
        self.assertFalse(classroom.memberships.filter(user=self.student).exists())

    def test_organization_flag_must_match_classroom_role(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.student, student=True)
        classroom = self.create_classroom(organization)
        response = self.client.post(
            reverse("users-manager:classroom-invite", kwargs={"pk": classroom.pk}),
            {"email": self.student.email, "role": ClassroomMembership.Role.TEACHER},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "não possui a flag de professor")

    def test_teacher_can_create_test_for_classroom(self) -> None:
        organization = self.create_organization()
        classroom = self.create_classroom(organization)
        response = self.client.post(
            reverse("users-manager:classroom-test-create", kwargs={"pk": classroom.pk}),
            {
                "title": "Diagnóstico de Álgebra",
                "instructions": "Responda sem consultar o material.",
                "max_score": 20,
                "is_published": "on",
            },
        )
        classroom_test = ClassroomTest.objects.get(title="Diagnóstico de Álgebra")
        self.assertEqual(classroom_test.classroom, classroom)
        self.assertEqual(classroom_test.created_by, self.owner)
        self.assertRedirects(
            response,
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}),
        )

    def test_student_cannot_create_classroom_test(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.student, student=True)
        classroom = self.create_classroom(organization)
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.student,
            role=ClassroomMembership.Role.STUDENT,
            status=MembershipStatus.ACTIVE,
            invited_by=self.owner,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("users-manager:classroom-test-create", kwargs={"pk": classroom.pk}),
            {"title": "Teste indevido", "max_score": 10, "is_published": "on"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ClassroomTest.objects.exists())

    def test_student_sees_published_test_but_not_draft(self) -> None:
        organization = self.create_organization()
        self.add_member(organization, self.student, student=True)
        classroom = self.create_classroom(organization)
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.student,
            role=ClassroomMembership.Role.STUDENT,
            status=MembershipStatus.ACTIVE,
            invited_by=self.owner,
        )
        ClassroomTest.objects.create(
            classroom=classroom,
            title="Teste publicado",
            created_by=self.owner,
            is_published=True,
        )
        ClassroomTest.objects.create(
            classroom=classroom,
            title="Rascunho do professor",
            created_by=self.owner,
            is_published=False,
        )
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk})
        )

        self.assertContains(response, "Teste publicado")
        self.assertNotContains(response, "Rascunho do professor")

    def test_user_can_create_self_assessment(self) -> None:
        response = self.client.post(
            reverse("users-manager:assessment-create"),
            {"focus": 4, "organization": 3, "comprehension": 5, "motivation": 4},
        )
        self.assertRedirects(response, reverse("users-manager:dashboard"))
        self.assertEqual(SelfAssessment.objects.get(user=self.owner).score, 80)
