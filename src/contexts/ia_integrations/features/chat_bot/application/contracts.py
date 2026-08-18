from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ChatRequest:
    message: str
    conversation_id: str
    user_id: str


@dataclass(frozen=True, slots=True)
class ChatResponse:
    message: str
    conversation_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentGateway(Protocol):
    async def ask(self, request: ChatRequest) -> ChatResponse: ...
