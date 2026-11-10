"""Django persistence adapter: access rules, serialization and transactions live here."""
import json
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from . import history
from .actions import validate_proposal, execute_proposal
from .queries import read_tool
from .auth import resolve_token, token_for
from ..exceptions import AgentUnavailable, ProposalRejected


def serialize(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def active_user(user_id):
    try:
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except (get_user_model().DoesNotExist, ValueError, TypeError):
        raise AgentUnavailable('Usuário indisponível.') from None
    if getattr(user, 'must_change_password', False):
        raise AgentUnavailable('Atualize sua senha antes de usar o assistente.')
    return user


class DjangoRepository:
    @database_sync_to_async
    def context(self, user_id):
        return {'user_id': active_user(user_id).pk}

    @database_sync_to_async
    def read(self, user_id, tool):
        user = active_user(user_id)
        try:
            return serialize(read_tool(user, tool))
        except (PermissionDenied, ValidationError, ValueError, TypeError):
            return {'error': 'Consulta inválida ou fora do escopo autorizado.'}

    @database_sync_to_async
    def validate(self, user_id, proposal):
        try:
            return serialize(validate_proposal(active_user(user_id), proposal))
        except (PermissionDenied, ValidationError, ValueError, TypeError) as exc:
            raise ProposalRejected('Proposta inválida ou fora do seu acesso.') from exc

    @database_sync_to_async
    def execute(self, user_id, generation, proposal):
        from contexts.ia_integrations.models import Conversation
        try:
            with transaction.atomic():
                user = active_user(user_id)
                conversation = Conversation.objects.select_for_update().get(user=user)
                if str(conversation.generation) != generation:
                    raise ProposalRejected('A conversa foi limpa. Solicite uma nova proposta.')
                return serialize(execute_proposal(user, proposal))
        except (PermissionDenied, ValidationError, ValueError, TypeError) as exc:
            raise ProposalRejected('Proposta inválida ou desatualizada.') from exc

    @database_sync_to_async
    def load(self, user_id):
        active_user(user_id)
        generation, rows = history.load(user_id)
        return generation, serialize(rows)

    @database_sync_to_async
    def append(self, user_id, generation, role, content, metadata=None):
        active_user(user_id)
        return history.append(user_id, generation, role, content, metadata)

    @database_sync_to_async
    def clear(self, user_id):
        active_user(user_id)
        return history.clear(user_id)

    @database_sync_to_async
    def page(self, user_id, generation, before):
        active_user(user_id)
        return serialize(history.page(user_id, generation, before))

    async def issue_token(self, user_id):
        return await token_for(user_id)

    @database_sync_to_async
    def authorize_token(self, token):
        return str(resolve_token(token).pk)

    @database_sync_to_async
    def read_by_token(self, token, tool):
        # Revalidate the capability on every tool call, not only on connection.
        return serialize(read_tool(resolve_token(token), tool))
