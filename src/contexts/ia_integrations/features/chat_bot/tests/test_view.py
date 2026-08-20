from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


class ChatBotViewTests(TestCase):
    def test_requires_authentication(self) -> None:
        response = self.client.get(reverse("ia-integrations:chat-bot"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('ia-integrations:chat-bot')}",
        )

    def test_renders_chat_interface_for_authenticated_user(self) -> None:
        user = get_user_model().objects.create_user(
            username="interface-user", password="safe-password"
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ia-integrations:chat-bot"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aprenda perguntando.")
        self.assertContains(response, 'data-websocket-path="/ws/ia-integrations/chat-bot/"')

    def test_diagnostic_mode_builds_personalized_ai_prompt(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="diagnostic-user",
            password="safe-password",
            onboarding_role=user_model.OnboardingRole.STUDENT,
            education_level=user_model.EducationLevel.UNDERGRADUATE,
            app_goal=user_model.AppGoal.PREPARE_EXAM,
            app_goal_details="Concurso público",
            onboarding_completed_at=timezone.now(),
        )
        self.client.force_login(user)

        response = self.client.get(
            f'{reverse("ia-integrations:chat-bot")}?mode=diagnostic'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Crie um teste diagnóstico personalizado",
            response.context["diagnostic_prompt"],
        )
        self.assertIn("Concurso público", response.context["diagnostic_prompt"])
