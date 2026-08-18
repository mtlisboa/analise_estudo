from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SessionAuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="matheus",
            email="matheus@example.com",
            password="senha-forte-123",
        )

    def test_dashboard_redirects_anonymous_user_to_login(self) -> None:
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("accounts:dashboard")}',
        )

    def test_landing_page_is_public(self) -> None:
        response = self.client.get(reverse("accounts:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cada aluno aprende de um jeito")
        self.assertContains(response, reverse("accounts:sign-up"))

    def test_login_creates_authenticated_session(self) -> None:
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "matheus", "password": "senha-forte-123"},
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_logout_accepts_post_and_removes_session(self) -> None:
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_rejects_get(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 405)

    def test_sign_up_creates_user_and_starts_session(self) -> None:
        response = self.client.post(
            reverse("accounts:sign-up"),
            {
                "username": "novo_usuario",
                "email": "novo@example.com",
                "password1": "uma-senha-segura-456",
                "password2": "uma-senha-segura-456",
            },
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertTrue(User.objects.filter(username="novo_usuario").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_sign_up_rejects_duplicate_email_case_insensitively(self) -> None:
        response = self.client.post(
            reverse("accounts:sign-up"),
            {
                "username": "outro_usuario",
                "email": "MATHEUS@example.com",
                "password1": "uma-senha-segura-456",
                "password2": "uma-senha-segura-456",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este e-mail já está em uso.")
        self.assertFalse(User.objects.filter(username="outro_usuario").exists())

    def test_sysadmin_cannot_use_common_login(self) -> None:
        sysadmin = User.objects.create_user(
            username="sistema",
            email="sistema@example.com",
            password="senha-sistema-123",
            system_role=User.SystemRole.SYSADMIN,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": sysadmin.username, "password": "senha-sistema-123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acesso exclusivo de sysadmin")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_only_sysadmin_can_use_separate_login(self) -> None:
        response = self.client.post(
            reverse("accounts:sysadmin-login"),
            {"username": self.user.username, "password": "senha-forte-123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exclusivo para administradores de sistema")

    def test_sysadmin_login_redirects_to_admin(self) -> None:
        sysadmin = User.objects.create_user(
            username="sistema",
            email="sistema@example.com",
            password="senha-sistema-123",
            system_role=User.SystemRole.SYSADMIN,
            is_staff=True,
        )

        response = self.client.post(
            reverse("accounts:sysadmin-login"),
            {"username": sysadmin.username, "password": "senha-sistema-123"},
        )

        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), sysadmin.pk)
