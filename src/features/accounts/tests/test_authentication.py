from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


class SessionAuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="matheus",
            email="matheus@example.com",
            password="senha-forte-123",
            onboarding_completed_at=timezone.now(),
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

    def test_authenticated_area_uses_vertical_sidebar(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, 'class="app-sidebar"')
        self.assertContains(response, "Organizações e turmas")
        self.assertContains(response, 'class="has-sidebar"')

    def test_public_login_keeps_horizontal_header(self) -> None:
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, 'class="site-header"')
        self.assertNotContains(response, 'class="app-sidebar"')

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

        self.assertRedirects(response, reverse("accounts:onboarding"))
        self.assertTrue(User.objects.filter(username="novo_usuario").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_first_login_redirects_to_onboarding(self) -> None:
        first_access_user = User.objects.create_user(
            username="primeiro_acesso",
            email="primeiro@example.com",
            password="senha-forte-123",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": first_access_user.username, "password": "senha-forte-123"},
        )

        self.assertRedirects(response, reverse("accounts:onboarding"))

    def test_onboarding_later_saves_profile_and_redirects_to_dashboard(self) -> None:
        user = User.objects.create_user(username="novo", password="senha-forte-123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:onboarding"),
            {
                "onboarding_role": User.OnboardingRole.STUDENT,
                "discovery_source": User.DiscoverySource.SEARCH,
                "education_level": User.EducationLevel.UNDERGRADUATE,
                "app_goal": User.AppGoal.ORGANIZE_STUDIES,
                "app_goal_details": "Criar uma rotina semanal.",
                "action": "later",
            },
        )

        self.assertRedirects(response, reverse("accounts:dashboard"))
        user.refresh_from_db()
        self.assertTrue(user.has_completed_onboarding)
        self.assertEqual(user.diagnostic_test_choice, User.DiagnosticTestChoice.LATER)

    def test_onboarding_start_test_redirects_to_ai_diagnostic(self) -> None:
        user = User.objects.create_user(username="aluna", password="senha-forte-123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:onboarding"),
            {
                "onboarding_role": User.OnboardingRole.STUDENT,
                "discovery_source": User.DiscoverySource.RECOMMENDATION,
                "education_level": User.EducationLevel.HIGH_SCHOOL,
                "app_goal": User.AppGoal.PREPARE_EXAM,
                "app_goal_details": "Preparação para o ENEM.",
                "action": "start-test",
            },
        )

        self.assertRedirects(response, f'{reverse("ia-integrations:chat-bot")}?mode=diagnostic')
        user.refresh_from_db()
        self.assertEqual(user.diagnostic_test_choice, User.DiagnosticTestChoice.STARTED)

    def test_completed_user_does_not_repeat_onboarding(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:onboarding"))

        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_other_goal_requires_details(self) -> None:
        user = User.objects.create_user(username="outro", password="senha-forte-123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:onboarding"),
            {
                "onboarding_role": User.OnboardingRole.OTHER,
                "discovery_source": User.DiscoverySource.OTHER,
                "education_level": User.EducationLevel.OTHER,
                "app_goal": User.AppGoal.OTHER,
                "app_goal_details": "",
                "action": "later",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Descreva brevemente o seu objetivo.")
        user.refresh_from_db()
        self.assertFalse(user.has_completed_onboarding)

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
