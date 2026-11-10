"""Single inference entry point for chat and assessment workflows."""
from asgiref.sync import async_to_sync
from django.conf import settings
from .exceptions import AgentUnavailable


def provider_name():
    name = settings.RAG_PROVIDER.strip().lower()
    if name not in ('ollama', 'mcp'):
        raise AgentUnavailable('Provedor RAG inválido. Configure ollama ou mcp.')
    return name


async def acomplete(messages, *, structured=False, on_partial=None, user_id=None, allow_question_tools=True):
    if provider_name() == 'ollama':
        from .providers.ollama import acomplete as invoke
        return await invoke(messages, structured=structured, on_partial=on_partial)
    from .providers.mcp import acomplete as invoke
    return await invoke(messages, structured=structured, on_partial=on_partial, user_id=user_id, allow_question_tools=allow_question_tools)


def complete(messages, *, structured=False, user_id=None):
    if provider_name() == 'ollama':
        from .providers.ollama import complete as invoke
        return invoke(messages, structured=structured)
    return async_to_sync(acomplete)(messages, structured=structured, user_id=user_id)
