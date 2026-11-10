"""Short-lived, user-bound capabilities. Never accept caller-selected identity."""
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.utils.crypto import constant_time_compare

SALT = 'lumini.rag.questions.read.v1'
TOKEN_TTL = 300


def issue_token(user):
    if not user.is_active or getattr(user, 'must_change_password', False):
        raise PermissionDenied('Usuário indisponível.')
    return signing.dumps({'sub': str(user.pk), 'auth': user.get_session_auth_hash(),
                          'scope': 'questions:read'}, salt=SALT)


def resolve_token(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=TOKEN_TTL)
        user = get_user_model().objects.get(pk=data['sub'], is_active=True)
        if (data.get('scope') != 'questions:read' or getattr(user, 'must_change_password', False)
                or not constant_time_compare(data.get('auth', ''), user.get_session_auth_hash())):
            raise PermissionDenied
        return user
    except (signing.BadSignature, KeyError, ValueError, TypeError, get_user_model().DoesNotExist):
        raise PermissionDenied('Credencial MCP inválida ou expirada.') from None


@database_sync_to_async
def token_for(user_id):
    try:
        return issue_token(get_user_model().objects.get(pk=user_id, is_active=True))
    except (get_user_model().DoesNotExist, ValueError, TypeError):
        raise PermissionDenied('Usuário indisponível.') from None
