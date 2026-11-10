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

class ProposalService:
    calls = []

    async def reply(self, request):
        self.calls.append(request)
        return ChatResponse('Revise a proposta.', request.conversation_id, {'proposal': {
            'action': 'create_question', 'subject': 'Matemática', 'topic': 'Soma',
            'question': {'statement': '2 + 2?', 'question_type': 'multiple_choice',
                         'options': ['4', '5'], 'correct_answer': '4', 'points': 1}}})


class ConfirmationTests(TransactionTestCase):
    async def test_confirmation_saves_once_and_keeps_history(self):
        from features.assessments.models import QuestionBankItem
        user = await get_user_model().objects.acreate_user(username='confirm-user')
        socket = WebsocketCommunicator(application, '/ws/ia-integrations/chat-bot/',
            headers=[(b'origin', b'http://localhost'), (b'host', b'localhost')])
        socket.scope['user'] = user
        ProposalService.calls = []
        with patch('contexts.ia_integrations.features.chat_bot.presentation.consumers.ChatBotConsumer.service_factory', return_value=ProposalService()):
            await socket.connect(); await socket.receive_json_from()
            await socket.send_json_to({'type':'chat.message', 'message':'Crie a questão', 'conversation_id':'a'})
            proposal = await socket.receive_json_from()
            self.assertEqual(await QuestionBankItem.objects.acount(), 0)
            event = {'type':'chat.confirm', 'token':proposal['metadata']['confirmation_token'], 'conversation_id':'a'}
            await socket.send_json_to(dict(event, token='forged'))
            self.assertEqual((await socket.receive_json_from())['code'], 'invalid_proposal')
            await socket.send_json_to(event)
            saved = await socket.receive_json_from()
            self.assertEqual(saved['type'], 'chat.response')
            self.assertTrue(saved['metadata']['url'].startswith('/'))
            self.assertEqual(await QuestionBankItem.objects.acount(), 1)
            await socket.send_json_to(event)
            self.assertEqual((await socket.receive_json_from())['code'], 'invalid_proposal')
            self.assertEqual(await QuestionBankItem.objects.acount(), 1)
            await socket.send_json_to({'type':'chat.message', 'message':'Explique', 'conversation_id':'a'})
            await socket.receive_json_from()
            self.assertTrue(ProposalService.calls[-1].history)
            await socket.send_json_to({'type':'chat.message', 'message':'Nova conversa', 'conversation_id':'b'})
            await socket.receive_json_from()
            self.assertFalse(ProposalService.calls[-1].history)
            await socket.disconnect()
