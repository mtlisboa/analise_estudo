from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
