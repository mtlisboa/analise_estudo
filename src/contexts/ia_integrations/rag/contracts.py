from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ChatRequest:
    message: str
    conversation_id: str
    user_id: str
    history: tuple = ()
    on_partial: Any = None


@dataclass(frozen=True, slots=True)
class ChatResponse:
    message: str
    conversation_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentGateway(Protocol):
    async def ask(self, request: ChatRequest) -> ChatResponse: ...


class CompletionProvider(Protocol):
    async def acomplete(self, messages: list[dict], *, structured: bool = False,
                        on_partial: Any = None, user_id: Any = None) -> Any: ...
