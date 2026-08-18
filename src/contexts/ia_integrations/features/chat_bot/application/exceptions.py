class ChatBotError(Exception):
    """Base error exposed by the chat bot application layer."""


class InvalidChatMessage(ChatBotError):
    """The incoming message does not satisfy the chat contract."""


class AgentUnavailable(ChatBotError):
    """The MCP agent could not answer the request."""
