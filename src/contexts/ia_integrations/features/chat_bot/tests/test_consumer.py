from unittest.mock import patch

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from config.asgi import application
from contexts.ia_integrations.features.chat_bot.application.contracts import (
    ChatResponse,
)


class FakeChatBotService:
    async def reply(self, request):
        return ChatResponse(
            message="Resposta MCP",
            conversation_id=request.conversation_id,
            metadata={"source": "mcp"},
        )


class ChatBotConsumerTests(TransactionTestCase):
    async def test_authenticated_user_can_exchange_messages(self) -> None:
        user = await get_user_model().objects.acreate_user(
            username="chat-user", password="not-used"
        )
        communicator = WebsocketCommunicator(
            application,
            "/ws/ia-integrations/chat-bot/",
            headers=[(b"origin", b"http://localhost"), (b"host", b"localhost")],
        )
        communicator.scope["user"] = user

        with patch(
            "contexts.ia_integrations.features.chat_bot.presentation.consumers."
            "ChatBotConsumer.service_factory",
            return_value=FakeChatBotService(),
        ):
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            self.assertEqual(await communicator.receive_json_from(), {"type": "chat.ready"})

            await communicator.send_json_to(
                {
                    "type": "chat.message",
                    "message": "Como melhorar meus estudos?",
                    "conversation_id": "thread-1",
                }
            )
            response = await communicator.receive_json_from()

            self.assertEqual(response["type"], "chat.response")
            self.assertEqual(response["message"], "Resposta MCP")
            self.assertEqual(response["conversation_id"], "thread-1")
            await communicator.disconnect()

    async def test_rejects_anonymous_connection(self) -> None:
        communicator = WebsocketCommunicator(
            application,
            "/ws/ia-integrations/chat-bot/",
            headers=[(b"origin", b"http://localhost"), (b"host", b"localhost")],
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)
