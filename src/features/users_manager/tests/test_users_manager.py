from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.users_manager.models import (
    Classroom,
    ClassroomMembership,
    EducationalRelationship,
    MembershipStatus,
    SelfAssessment,
)

User = get_user_model()


class UsersManagerTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="matheus",
            email="matheus@example.com",
            password="senha-forte-123",
        )
        self.other = User.objects.create_user(
            username="professora",
            email="professora@example.com",
            password="senha-forte-456",
        )
        self.client.force_login(self.user)

    def test_manager_dashboard_requires_authentication(self) -> None:
        self.client.logout()

        response = self.client.get(reverse("users-manager:dashboard"))

        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("users-manager:dashboard")}',
        )

    def test_student_can_request_teacher_relationship(self) -> None:
        response = self.client.post(
            reverse("users-manager:relationship-create"),
            {"email": self.other.email, "position": "STUDENT"},
        )

        self.assertRedirects(response, reverse("users-manager:dashboard"))
        relationship = EducationalRelationship.objects.get()
        self.assertEqual(relationship.teacher, self.other)
        self.assertEqual(relationship.student, self.user)
        self.assertEqual(relationship.requested_by, self.user)
        self.assertEqual(relationship.status, MembershipStatus.PENDING)

    def test_relationship_recipient_can_accept_request(self) -> None:
        relationship = EducationalRelationship.objects.create(
            teacher=self.user,
            student=self.other,
            requested_by=self.user,
        )
        self.client.force_login(self.other)

        response = self.client.post(
            reverse(
                "users-manager:relationship-decide",
                kwargs={"pk": relationship.pk, "decision": "accept"},
            )
        )

        self.assertRedirects(response, reverse("users-manager:dashboard"))
        relationship.refresh_from_db()
        self.assertEqual(relationship.status, MembershipStatus.ACTIVE)
        self.assertTrue(self.user.is_teacher)
        self.assertTrue(self.other.is_student)

    def test_requester_cannot_accept_own_relationship_request(self) -> None:
        relationship = EducationalRelationship.objects.create(
            teacher=self.user,
            student=self.other,
            requested_by=self.user,
        )

        response = self.client.post(
            reverse(
                "users-manager:relationship-decide",
                kwargs={"pk": relationship.pk, "decision": "accept"},
            )
        )

        self.assertEqual(response.status_code, 403)
        relationship.refresh_from_db()
        self.assertEqual(relationship.status, MembershipStatus.PENDING)

    def test_create_classroom_adds_creator_as_teacher(self) -> None:
        response = self.client.post(
            reverse("users-manager:classroom-create"),
            {"name": "Cálculo I", "description": "Turma da manhã"},
        )

        classroom = Classroom.objects.get(name="Cálculo I")
        self.assertRedirects(
            response,
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}),
        )
        membership = ClassroomMembership.objects.get(classroom=classroom, user=self.user)
        self.assertEqual(membership.role, ClassroomMembership.Role.TEACHER)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

    def test_teacher_can_invite_student_to_classroom(self) -> None:
        classroom = Classroom.objects.create(name="Álgebra", owner=self.user)
        ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.user,
            role=ClassroomMembership.Role.TEACHER,
            status=MembershipStatus.ACTIVE,
            invited_by=self.user,
        )

        response = self.client.post(
            reverse("users-manager:classroom-invite", kwargs={"pk": classroom.pk}),
            {"email": self.other.email, "role": ClassroomMembership.Role.STUDENT},
        )

        self.assertRedirects(
            response,
            reverse("users-manager:classroom-detail", kwargs={"pk": classroom.pk}),
        )
        invitation = ClassroomMembership.objects.get(classroom=classroom, user=self.other)
        self.assertEqual(invitation.status, MembershipStatus.PENDING)
        self.assertEqual(invitation.role, ClassroomMembership.Role.STUDENT)

    def test_invited_user_can_accept_classroom_invitation(self) -> None:
        classroom = Classroom.objects.create(name="Física", owner=self.user)
        invitation = ClassroomMembership.objects.create(
            classroom=classroom,
            user=self.other,
            role=ClassroomMembership.Role.STUDENT,
            invited_by=self.user,
        )
        self.client.force_login(self.other)

        response = self.client.post(
            reverse(
                "users-manager:classroom-invitation-decide",
                kwargs={"pk": invitation.pk, "decision": "accept"},
            )
        )

        self.assertRedirects(response, reverse("users-manager:dashboard"))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, MembershipStatus.ACTIVE)

    def test_user_can_create_self_assessment(self) -> None:
        response = self.client.post(
            reverse("users-manager:assessment-create"),
            {
                "focus": 4,
                "organization": 3,
                "comprehension": 5,
                "motivation": 4,
                "notes": "Semana produtiva.",
            },
        )

        self.assertRedirects(response, reverse("users-manager:dashboard"))
        assessment = SelfAssessment.objects.get(user=self.user)
        self.assertEqual(assessment.score, 80)

    def test_sysadmin_cannot_be_invited_to_relationship(self) -> None:
        sysadmin = User.objects.create_user(
            username="sistema",
            email="sistema@example.com",
            system_role=User.SystemRole.SYSADMIN,
        )

        response = self.client.post(
            reverse("users-manager:relationship-create"),
            {"email": sysadmin.email, "position": "TEACHER"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contas de sistema não podem participar")
        self.assertFalse(EducationalRelationship.objects.exists())
