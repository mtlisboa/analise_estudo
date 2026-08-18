from django.test import SimpleTestCase

from ..application.contracts import ChatRequest, ChatResponse
from ..application.exceptions import InvalidChatMessage
from ..application.service import ChatBotService


class FakeAgentGateway:
    def __init__(self) -> None:
        self.last_request: ChatRequest | None = None

    async def ask(self, request: ChatRequest) -> ChatResponse:
        self.last_request = request
        return ChatResponse("Resposta da documentação", request.conversation_id)


class ChatBotServiceTests(SimpleTestCase):
    async def test_normalizes_message_and_delegates_to_agent(self) -> None:
        gateway = FakeAgentGateway()
        service = ChatBotService(gateway)

        response = await service.reply(ChatRequest("  dúvida  ", "thread-1", "42"))

        self.assertEqual(response.message, "Resposta da documentação")
        self.assertEqual(gateway.last_request.message, "dúvida")

    async def test_rejects_empty_message(self) -> None:
        service = ChatBotService(FakeAgentGateway())

        with self.assertRaises(InvalidChatMessage):
            await service.reply(ChatRequest("   ", "thread-1", "42"))
