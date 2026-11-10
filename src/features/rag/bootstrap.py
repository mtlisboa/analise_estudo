"""Single inference entry point for chat and assessment workflows."""
from asgiref.sync import async_to_sync
from django.conf import settings
from .exceptions import AgentUnavailable
from .validation import validate_output


async def token_for(user_id):
    return await build_repository().issue_token(user_id)


def provider_name():
    name = settings.RAG_PROVIDER.strip().lower()
    if name not in ('ollama', 'mcp'):
        raise AgentUnavailable('Provedor RAG inválido. Configure ollama ou mcp.')
    return name


async def acomplete(messages, *, structured=False, on_partial=None, user_id=None, allow_question_tools=True):
    if provider_name() == 'ollama':
        from .infrastructure.providers.ollama import acomplete as invoke
        result = await invoke(messages, structured=structured, on_partial=on_partial)
        validate_output(result)
        return result
    from .infrastructure.providers.mcp import acomplete as invoke
    result = await invoke(messages, structured=structured, on_partial=on_partial, user_id=user_id, allow_question_tools=allow_question_tools, capability_provider=token_for)
    validate_output(result)
    return result


def complete(messages, *, structured=False, user_id=None):
    if provider_name() == 'ollama':
        from .infrastructure.providers.ollama import complete as invoke
        result = invoke(messages, structured=structured)
        validate_output(result)
        return result
    return async_to_sync(acomplete)(messages, structured=structured, user_id=user_id)


class ConfiguredProvider:
    @property
    def name(self):
        return provider_name()

    async def acomplete(self, messages, **kwargs):
        return await acomplete(messages, **kwargs)


def build_repository():
    from django.utils.module_loading import import_string
    repository_class = import_string(settings.RAG_REPOSITORY_CLASS)
    return repository_class()


from .orchestrator import AssistantGateway as CoreGateway, compact_result


class AssistantGateway(CoreGateway):
    """Composition boundary for Django callers; core also accepts fully custom adapters."""
    def __init__(self, provider=None, repository=None, knowledge=None):
        from .infrastructure.knowledge import FileKnowledge
        super().__init__(provider or ConfiguredProvider(), repository or build_repository(),
                         knowledge or FileKnowledge())
