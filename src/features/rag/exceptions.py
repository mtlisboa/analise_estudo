class ChatBotError(Exception):
    """Base error exposed by the chat bot application layer."""


class InvalidChatMessage(ChatBotError):
    """The incoming message does not satisfy the chat contract."""


class AgentUnavailable(ChatBotError):
    """The language model could not answer the request."""


class ProposalRejected(ChatBotError):
    """A proposal violated a domain rule or its source is no longer current."""


class InvalidGeneration(AgentUnavailable):
    """Generated content failed validation; never persist it as a completed reply."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__('A resposta gerada foi descartada por repetição, tamanho excessivo ou orientação não verificada. Tente reformular o pedido.')
