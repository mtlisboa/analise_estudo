from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.users_manager.models import Organization, OrganizationMembership

User = get_user_model()


class OrganizationSettingsTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner", password="senha-forte-123")
        self.other = User.objects.create_user(username="other", password="senha-forte-456")
        self.organization = Organization.objects.create(name="Escola Lumini", owner=self.owner)
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            is_teacher=True,
            added_by=self.owner,
        )

    def test_owner_can_change_own_role_to_student(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("organization-settings:detail", kwargs={"pk": self.organization.pk}),
            {"name": "Escola Lumini", "description": "", "is_student": "on"},
        )

        self.assertRedirects(
            response,
            reverse("users-manager:organization-detail", kwargs={"pk": self.organization.pk}),
        )
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_teacher)
        self.assertTrue(self.membership.is_student)

    def test_owner_can_select_both_roles(self) -> None:
        self.client.force_login(self.owner)

        self.client.post(
            reverse("organization-settings:detail", kwargs={"pk": self.organization.pk}),
            {
                "name": "Escola Lumini",
                "description": "",
                "is_teacher": "on",
                "is_student": "on",
            },
        )

        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_teacher)
        self.assertTrue(self.membership.is_student)

    def test_at_least_one_role_is_required(self) -> None:
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("organization-settings:detail", kwargs={"pk": self.organization.pk}),
            {"name": "Escola Lumini", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Escolha pelo menos um papel")
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_teacher)

    def test_non_owner_cannot_open_settings(self) -> None:
        self.client.force_login(self.other)

        response = self.client.get(
            reverse("organization-settings:detail", kwargs={"pk": self.organization.pk})
        )

        self.assertEqual(response.status_code, 403)
