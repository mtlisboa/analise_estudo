from ..application.contracts import ChatRequest, ChatResponse


class MockAgentGateway:
    """Deterministic assistant used by public demos without an external MCP server."""

    async def ask(self, request: ChatRequest) -> ChatResponse:
        message = request.message.casefold()
        if "diagnóstico" in message or "teste" in message:
            answer = (
                "Vamos iniciar o diagnóstico demonstrativo. Em uma escala de 1 a 5, "
                "quanto você consegue explicar com suas próprias palavras o último "
                "conteúdo que estudou?"
            )
        elif "matem" in message:
            answer = (
                "Nos dados de demonstração, Matemática evoluiu de forma consistente. "
                "Sugiro uma sessão curta de recordação ativa seguida por dois problemas "
                "de aplicação e uma revisão dos erros."
            )
        else:
            answer = (
                "Esta é uma resposta simulada do assistente Lumini. Posso demonstrar um "
                "diagnóstico, sugerir uma revisão de Matemática ou montar um próximo passo "
                "de estudos com base nos dados exibidos no painel."
            )
        return ChatResponse(
            message=answer,
            conversation_id=request.conversation_id,
            metadata={"source": "mock", "deploy_mode": "MOCK"},
        )
