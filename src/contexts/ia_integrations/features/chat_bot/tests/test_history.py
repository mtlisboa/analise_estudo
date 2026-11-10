import asyncio
from unittest.mock import patch
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from config.asgi import application
from contexts.ia_integrations.models import ChatMessage
from .test_consumer import FakeChatBotService

FACTORY = 'contexts.ia_integrations.features.chat_bot.presentation.consumers.ChatBotConsumer.service_factory'

class SlowService:
    started = None
    async def reply(self, request):
        if self.started:
            self.started.set()
        await asyncio.sleep(10)

class HistoryTests(TransactionTestCase):
    async def connection(self, user):
        socket = WebsocketCommunicator(application, '/ws/ia-integrations/chat-bot/', headers=[(b'origin', b'http://localhost'), (b'host', b'localhost')])
        socket.scope['user'] = user
        await socket.connect()
        return socket, await socket.receive_json_from()

    async def test_reload_isolation_and_real_delete(self):
        user = await get_user_model().objects.acreate_user(username='saved')
        other = await get_user_model().objects.acreate_user(username='isolated')
        socket, ready = await self.connection(user)
        with patch(FACTORY, return_value=FakeChatBotService()):
            await socket.send_json_to({'type':'chat.message', 'message':'Minha dúvida', 'conversation_id':ready['conversation_id']})
            self.assertEqual((await socket.receive_json_from())['type'], 'chat.response')
        await socket.disconnect()
        socket, reloaded = await self.connection(user)
        self.assertEqual([m['content'] for m in reloaded['messages']], ['Minha dúvida', 'Resposta MCP'])
        foreign, foreign_ready = await self.connection(other)
        self.assertEqual(foreign_ready['messages'], [])
        await foreign.disconnect()
        await socket.send_json_to({'type':'chat.clear'})
        cleared = await socket.receive_json_from()
        self.assertNotEqual(cleared['conversation_id'], ready['conversation_id'])
        self.assertEqual(await ChatMessage.objects.acount(), 0)
        await socket.disconnect()
        socket, reloaded = await self.connection(user)
        self.assertEqual(reloaded['messages'], [])
        await socket.disconnect()

    @override_settings(IA_CHAT_TIMEOUT_SECONDS=0.05)
    async def test_global_deadline_stops_waiting(self):
        user = await get_user_model().objects.acreate_user(username='timeout')
        socket, ready = await self.connection(user)
        with patch(FACTORY, return_value=SlowService()):
            await socket.send_json_to({'type':'chat.message', 'message':'Demorada', 'conversation_id':ready['conversation_id']})
            response = await socket.receive_json_from()
        self.assertEqual(response['code'], 'timeout')
        with patch(FACTORY, return_value=FakeChatBotService()):
            await socket.send_json_to({'type':'chat.message', 'message':'De novo', 'conversation_id':ready['conversation_id']})
            self.assertEqual((await socket.receive_json_from())['type'], 'chat.response')
        await socket.disconnect()

    async def test_clear_cancels_running_answer(self):
        user = await get_user_model().objects.acreate_user(username='cancel')
        socket, ready = await self.connection(user)
        slow = SlowService(); slow.started = asyncio.Event()
        with patch(FACTORY, return_value=slow):
            await socket.send_json_to({'type':'chat.message', 'message':'Demorada', 'conversation_id':ready['conversation_id']})
            await asyncio.wait_for(slow.started.wait(), 1)
            await socket.send_json_to({'type':'chat.clear'})
            self.assertEqual((await socket.receive_json_from())['type'], 'chat.cleared')
        self.assertEqual(await ChatMessage.objects.acount(), 0)
        await socket.disconnect()

    async def test_old_tab_cannot_restore_deleted_messages(self):
        user = await get_user_model().objects.acreate_user(username='two-tabs')
        first, ready = await self.connection(user)
        second, _ = await self.connection(user)
        await second.send_json_to({'type':'chat.clear'})
        await second.receive_json_from()
        with patch(FACTORY, return_value=FakeChatBotService()):
            await first.send_json_to({'type':'chat.message','message':'Antiga','conversation_id':ready['conversation_id']})
            self.assertEqual((await first.receive_json_from())['code'], 'stale_conversation')
        self.assertEqual(await ChatMessage.objects.acount(), 0)
        await first.disconnect(); await second.disconnect()

    async def test_history_pagination_does_not_drop_older_messages(self):
        from contexts.ia_integrations.models import Conversation
        user = await get_user_model().objects.acreate_user(username='pages')
        conversation = await Conversation.objects.acreate(user=user)
        await ChatMessage.objects.abulk_create([ChatMessage(conversation=conversation, role='user', content=str(i)) for i in range(201)])
        socket, ready = await self.connection(user)
        self.assertEqual(len(ready['messages']), 200)
        self.assertEqual(ready['messages'][0]['content'], '1')
        await socket.send_json_to({'type':'chat.history','before':ready['messages'][0]['id']})
        older = await socket.receive_json_from()
        self.assertEqual([m['content'] for m in older['messages']], ['0'])
        await socket.disconnect()

    async def test_mode_survives_reload_and_invalid_mode_is_not_saved(self):
        user = await get_user_model().objects.acreate_user(username='mode-history')
        socket, ready = await self.connection(user)
        await socket.send_json_to({'type':'chat.message', 'message':'Oi', 'mode':'invalid'})
        self.assertEqual((await socket.receive_json_from())['code'], 'invalid_mode')
        self.assertEqual(await ChatMessage.objects.acount(), 0)
        with patch(FACTORY, return_value=FakeChatBotService()):
            await socket.send_json_to({'type':'chat.message', 'message':'Monte uma questão', 'mode':'assembly'})
            self.assertEqual((await socket.receive_json_from())['metadata']['mode'], 'assembly')
        await socket.disconnect()
        socket, ready = await self.connection(user)
        self.assertEqual([m['metadata']['mode'] for m in ready['messages']], ['assembly', 'assembly'])
        await socket.disconnect()

    async def test_repetitive_output_is_not_persisted_as_an_answer(self):
        from unittest.mock import AsyncMock
        from features.rag.tests.test_validation import LOOP
        user = await get_user_model().objects.acreate_user(username='validated-history')
        socket, ready = await self.connection(user)
        with patch('features.rag.bootstrap.acomplete', new_callable=AsyncMock, return_value=LOOP):
            await socket.send_json_to({'type':'chat.message', 'message':'Como criar uma atividade?', 'mode':'doubts'})
            response = await socket.receive_json_from()
            if response['type'] == 'chat.delta':
                response = await socket.receive_json_from()
            self.assertEqual(response['type'], 'chat.response')
            self.assertEqual(response['metadata']['source'], 'documentation')
            await socket.send_json_to({'type':'chat.message', 'message':'Crie uma questão', 'mode':'assembly'})
            self.assertEqual((await socket.receive_json_from())['type'], 'chat.error')
        answers = [row async for row in ChatMessage.objects.filter(role='assistant')]
        self.assertEqual(len(answers), 1)
        self.assertNotIn('Adicionar a atividade', answers[0].content)
        self.assertIn('Consulta direta ao manual', answers[0].content)
        await socket.disconnect()
