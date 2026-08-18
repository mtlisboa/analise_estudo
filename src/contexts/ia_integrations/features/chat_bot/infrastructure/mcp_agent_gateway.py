import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from mcp import Client

from ..application.contracts import ChatRequest, ChatResponse
from ..application.exceptions import AgentUnavailable


class McpAgentGateway:
    """Calls one AI-agent tool exposed by a remote MCP server."""

    def __init__(self, server_url: str, tool_name: str, timeout_seconds: float) -> None:
        self._server_url = server_url.strip()
        self._tool_name = tool_name.strip()
        self._timeout_seconds = timeout_seconds

    async def ask(self, request: ChatRequest) -> ChatResponse:
        if not self._server_url:
            raise AgentUnavailable("IA_MCP_SERVER_URL não foi configurada.")
        if not self._tool_name:
            raise AgentUnavailable("IA_MCP_CHAT_TOOL não foi configurada.")

        arguments = {
            "message": request.message,
            "conversation_id": request.conversation_id,
            "user_id": request.user_id,
        }

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with Client(self._server_url) as client:
                    result = await client.call_tool(self._tool_name, arguments)
        except TimeoutError as exc:
            raise AgentUnavailable("O agente de IA excedeu o tempo limite.") from exc
        except Exception as exc:
            raise AgentUnavailable("Não foi possível consultar o agente de IA.") from exc

        if result.is_error:
            raise AgentUnavailable("O agente de IA retornou um erro.")

        message = self._extract_message(result.structured_content, result.content)
        if not message:
            raise AgentUnavailable("O agente de IA retornou uma resposta vazia.")

        return ChatResponse(
            message=message,
            conversation_id=request.conversation_id,
            metadata={"source": "mcp", "tool": self._tool_name},
        )

    @classmethod
    def _extract_message(
        cls,
        structured_content: Mapping[str, Any] | None,
        content: Sequence[Any],
    ) -> str:
        if structured_content:
            for key in ("message", "answer", "result"):
                value = structured_content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        text_parts = [
            block.text.strip()
            for block in content
            if isinstance(getattr(block, "text", None), str) and block.text.strip()
        ]
        return "\n".join(text_parts)
