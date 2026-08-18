from .contracts import AgentGateway, ChatRequest, ChatResponse
from .exceptions import InvalidChatMessage


class ChatBotService:
    MAX_MESSAGE_LENGTH = 8_000

    def __init__(self, agent_gateway: AgentGateway) -> None:
        self._agent_gateway = agent_gateway

    async def reply(self, request: ChatRequest) -> ChatResponse:
        message = request.message.strip()
        if not message:
            raise InvalidChatMessage("A mensagem não pode estar vazia.")
        if len(message) > self.MAX_MESSAGE_LENGTH:
            raise InvalidChatMessage(
                f"A mensagem deve ter no máximo {self.MAX_MESSAGE_LENGTH} caracteres."
            )

        normalized_request = ChatRequest(
            message=message,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
        )
        return await self._agent_gateway.ask(normalized_request)
