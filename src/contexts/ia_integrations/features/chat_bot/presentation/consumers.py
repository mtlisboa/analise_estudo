from typing import Any
from uuid import uuid4

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from ..application.contracts import ChatRequest
from ..application.exceptions import AgentUnavailable, InvalidChatMessage
from ..application.service import ChatBotService
from ..infrastructure.mcp_agent_gateway import McpAgentGateway


def build_chat_bot_service() -> ChatBotService:
    gateway = McpAgentGateway(
        server_url=settings.IA_MCP_SERVER_URL,
        tool_name=settings.IA_MCP_CHAT_TOOL,
        timeout_seconds=settings.IA_MCP_TIMEOUT_SECONDS,
    )
    return ChatBotService(gateway)


class ChatBotConsumer(AsyncJsonWebsocketConsumer):
    service_factory = staticmethod(build_chat_bot_service)

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        await self.accept()
        await self.send_json({"type": "chat.ready"})

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
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
        if not isinstance(conversation_id, str):
            await self._send_error(
                "invalid_conversation_id",
                "O campo 'conversation_id' deve ser texto.",
            )
            return

        user = self.scope["user"]
        request = ChatRequest(
            message=message,
            conversation_id=conversation_id,
            user_id=str(user.pk),
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

        await self.send_json(
            {
                "type": "chat.response",
                "message": response.message,
                "conversation_id": response.conversation_id,
                "metadata": response.metadata,
            }
        )

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
