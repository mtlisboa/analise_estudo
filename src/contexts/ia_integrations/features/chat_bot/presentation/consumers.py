from typing import Any
from uuid import uuid4

from channels.generic.websocket import AsyncJsonWebsocketConsumer
import time
import asyncio
from django.conf import settings
from ..application import history as history_store
import json
import logging
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from ..application.actions import execute_proposal

from ..application.contracts import ChatRequest
from ..application.exceptions import AgentUnavailable, InvalidChatMessage
from ..application.service import ChatBotService
from contexts.ia_integrations.rag.orchestrator import AssistantGateway


def build_chat_bot_service() -> ChatBotService:
    return ChatBotService(AssistantGateway())


class ChatBotConsumer(AsyncJsonWebsocketConsumer):
    service_factory = staticmethod(build_chat_bot_service)

    async def connect(self) -> None:
        self.task = None
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_active or getattr(user, "must_change_password", False):
            await self.close(code=4401)
            return

        self.task = None
        self.pending = None
        self.conversation_id, rows = await database_sync_to_async(history_store.load)(user.pk)
        self.history = [{'role': r['role'], 'content': r['content']} for r in rows[-8:]]
        await self.accept()
        await self.send_json({"type": "chat.ready", "conversation_id": self.conversation_id,
                              "messages": rows, "timeout_seconds": settings.IA_CHAT_TIMEOUT_SECONDS})

    async def disconnect(self, code):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if isinstance(content, dict) and content.get('type') == 'chat.clear':
            if self.task and not self.task.done():
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
            self.pending = None
            self.history = []
            self.conversation_id = await database_sync_to_async(history_store.clear)(self.scope['user'].pk)
            await self.send_json({'type': 'chat.cleared', 'conversation_id': self.conversation_id})
            return
        if isinstance(content, dict) and content.get('type') == 'chat.history':
            before = content.get('before')
            if type(before) is int and before > 0:
                rows = await database_sync_to_async(history_store.page)(self.scope['user'].pk, self.conversation_id, before)
                await self.send_json({'type': 'chat.history', 'conversation_id': self.conversation_id, 'messages': rows})
            return
        if self.task and not self.task.done():
            await self._send_error('busy', 'Uma resposta está em andamento. Aguarde ou limpe a conversa.', self.conversation_id)
            return
        if isinstance(content, dict) and content.get('type') == 'chat.message':
            self.task = asyncio.create_task(self._respond(content))
            return
        if isinstance(content, dict) and content.get('type') == 'chat.confirm':
            await self.confirm(content)
            return
        await self._send_error('invalid_event', 'Evento de chat inválido.')

    async def _respond(self, content):
        try:
            async with asyncio.timeout(settings.IA_CHAT_TIMEOUT_SECONDS):
                await self._message(content)
        except TimeoutError:
            await self._send_error('timeout', 'A geração excedeu o prazo total e a conexão com o modelo foi encerrada. Tente dividir o pedido em partes menores.', self.conversation_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception('Chat request failed')
            await self._send_error('agent_unavailable', 'Não foi possível concluir a resposta. Tente novamente.', self.conversation_id)

    async def _message(self, content: Any) -> None:
        if isinstance(content, dict) and content.get("type") == "chat.confirm":
            await self.confirm(content)
            return
        if not isinstance(content, dict) or content.get("type") != "chat.message":
            await self._send_error(
                "invalid_event", "O evento deve ter o tipo 'chat.message'."
            )
            return

        message = content.get("message")
        if not isinstance(message, str):
            await self._send_error("invalid_message", "O campo 'message' deve ser texto.")
            return

        conversation_id = self.conversation_id
        if content.get('conversation_id') not in (None, conversation_id):
            await self._send_error('stale_conversation', 'A conversa mudou. Recarregue o chat.', content.get('conversation_id'))
            return
        message = message.strip()
        if not message or len(message) > ChatBotService.MAX_MESSAGE_LENGTH:
            await self._send_error('invalid_message', 'Escreva uma mensagem de até 8000 caracteres.', conversation_id)
            return
        if not await database_sync_to_async(history_store.append)(self.scope['user'].pk, conversation_id, 'user', message):
            await self._send_error('stale_conversation', 'A conversa foi limpa em outra aba. Recarregue o chat.', conversation_id)
            return
        # A new request invalidates an older unaccepted proposal.
        self.pending = None
        user = self.scope["user"]
        request = ChatRequest(
            message=message,
            conversation_id=conversation_id,
            user_id=str(user.pk),
            history=tuple(self.history),
            on_partial=self._partial,
        )

        try:
            response = await self.service_factory().reply(request)
        except InvalidChatMessage as exc:
            await self._send_error("invalid_message", str(exc), conversation_id)
            return
        except AgentUnavailable:
            await self._send_error(
                "agent_unavailable",
                "O assistente está temporariamente indisponível.",
                conversation_id,
            )
            return

        except Exception:
            logging.getLogger(__name__).exception("Assistant request failed")
            await self._send_error("agent_unavailable", "Não foi possível concluir a consulta. Tente novamente.", conversation_id)
            return

        if not await database_sync_to_async(history_store.append)(user.pk, conversation_id, 'assistant', response.message, response.metadata):
            await self._send_error('stale_conversation', 'A conversa foi limpa em outra aba. Recarregue o chat.', conversation_id)
            return
        self.history.extend([{"role": "user", "content": message[:8000]},
                             {"role": "assistant", "content": json.dumps({"message": response.message, "proposal": response.metadata.get("proposal")}, ensure_ascii=False)[:16000]}])
        self.history = self.history[-8:]
        while len(self.history) > 2 and sum(len(m["content"]) for m in self.history) > 24000:
            self.history = self.history[2:]
        if response.metadata.get('proposal'):
            token = str(uuid4())
            self.pending = (token, response.metadata['proposal'], time.monotonic(), conversation_id)
            response.metadata['confirmation_token'] = token
        await self.send_json(
            {
                "type": "chat.response",
                "message": response.message,
                "conversation_id": response.conversation_id,
                "metadata": response.metadata,
            }
        )

    async def _partial(self, text):
        await self.send_json({'type': 'chat.delta', 'conversation_id': self.conversation_id, 'message': text})

    async def confirm(self, content):
        pending = self.pending
        if not pending or content.get('token') != pending[0] or content.get('conversation_id') != pending[3] or time.monotonic() - pending[2] > 600:
            await self._send_error('invalid_proposal', 'A proposta expirou ou já foi usada. Solicite uma nova.', content.get('conversation_id'))
            return
        self.pending = None
        try:
            result = await database_sync_to_async(self._execute)(pending[1])
        except (ValidationError, ValueError, TypeError) as exc:
            await self._send_error('invalid_proposal', 'Não foi possível salvar: ' + '; '.join(getattr(exc, 'messages', ['Proposta inválida.'])), pending[3])
            return
        except Exception:
            logging.getLogger(__name__).exception("Assistant action failed")
            await self._send_error('action_failed', 'Não foi possível salvar a proposta. Nenhuma alteração parcial foi mantida.', pending[3])
            return
        await database_sync_to_async(history_store.append)(self.scope['user'].pk, pending[3], 'assistant', result['message'], {'url': result['url']})
        self.history.append({'role': 'assistant', 'content': result['message']})
        await self.send_json({'type': 'chat.response', 'conversation_id': pending[3], 'message': result['message'], 'metadata': {'url': result['url']}})

    def _execute(self, proposal):
        user = get_user_model().objects.get(pk=self.scope['user'].pk, is_active=True)
        from django.db import transaction
        from contexts.ia_integrations.models import Conversation
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(user=user)
            if str(conversation.generation) != self.conversation_id:
                raise ValidationError('A conversa foi limpa. Solicite uma nova proposta.')
            return execute_proposal(user, proposal)

    async def _send_error(
        self, code: str, message: str, conversation_id: str | None = None
    ) -> None:
        payload: dict[str, Any] = {
            "type": "chat.error",
            "code": code,
            "message": message,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        await self.send_json(payload)

