from typing import Any
from uuid import uuid4

from channels.generic.websocket import AsyncJsonWebsocketConsumer
import time
import json
import logging
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from ..application.actions import execute_proposal

from ..application.contracts import ChatRequest
from ..application.exceptions import AgentUnavailable, InvalidChatMessage
from ..application.service import ChatBotService
from ..infrastructure.assistant_gateway import AssistantGateway


def build_chat_bot_service() -> ChatBotService:
    return ChatBotService(AssistantGateway())


class ChatBotConsumer(AsyncJsonWebsocketConsumer):
    service_factory = staticmethod(build_chat_bot_service)

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_active or getattr(user, "must_change_password", False):
            await self.close(code=4401)
            return

        self.history = []
        self.pending = None
        self.conversation_id = None
        await self.accept()
        await self.send_json({"type": "chat.ready"})

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
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

        conversation_id = content.get("conversation_id") or str(uuid4())
        if not isinstance(conversation_id, str) or len(conversation_id) > 128:
            await self._send_error(
                "invalid_conversation_id",
                "O campo 'conversation_id' deve ser texto.",
            )
            return

        if conversation_id != self.conversation_id:
            self.history = []
            self.pending = None
            self.conversation_id = conversation_id
        # A new request invalidates an older unaccepted proposal.
        self.pending = None
        user = self.scope["user"]
        request = ChatRequest(
            message=message,
            conversation_id=conversation_id,
            user_id=str(user.pk),
            history=tuple(self.history),
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
        self.history.append({'role': 'assistant', 'content': result['message']})
        await self.send_json({'type': 'chat.response', 'conversation_id': pending[3], 'message': result['message'], 'metadata': {'url': result['url']}})

    def _execute(self, proposal):
        user = get_user_model().objects.get(pk=self.scope['user'].pk, is_active=True)
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

