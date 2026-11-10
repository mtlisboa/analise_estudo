"""Read-only MCP tools served on /mcp/questions by the existing ASGI process."""
from typing import Any
from contextvars import ContextVar
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http.request import split_domain_port, validate_host
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from ..bootstrap import build_repository

credential = ContextVar('rag_mcp_credential', default='')
mcp = FastMCP('Lumini Question Bank', stateless_http=True, json_response=True,
    streamable_http_path='/mcp/questions',
    # Host validation below uses the same allowlist as Django, including production domains.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


async def query(tool):
    return await build_repository().read_by_token(credential.get(), tool)


@mcp.tool()
async def search_questions(query_text: str = '') -> dict[str, Any]:
    """Search the authenticated user's available question bank (up to 30 results)."""
    return await query({'name': 'search_questions', 'query': query_text})


@mcp.tool()
async def get_question(question_id: int) -> dict[str, Any]:
    """Read a permitted question in full before proposing an edit or reusing it."""
    return await query({'name': 'get_question', 'id': question_id})


@mcp.tool()
async def get_questionnaire(questionnaire_id: int) -> dict[str, Any]:
    """Read an existing questionnaire owned by the authenticated user."""
    return await query({'name': 'get_questionnaire', 'id': questionnaire_id})


class AuthenticatedMCP:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        host = headers.get(b'host', b'').decode('latin1')
        domain, _ = split_domain_port(host)
        if not domain or not validate_host(domain, settings.ALLOWED_HOSTS):
            return await JSONResponse({'error': 'Host inválido.'}, status_code=400)(scope, receive, send)
        # This is a server-to-server endpoint; browser origins are deliberately unsupported.
        if b'origin' in headers:
            return await JSONResponse({'error': 'Origem não permitida.'}, status_code=403)(scope, receive, send)
        auth = headers.get(b'authorization', b'').decode('latin1')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        try:
            await build_repository().authorize_token(token)
        except PermissionDenied:
            return await JSONResponse({'error': 'Credencial inválida ou expirada.'}, status_code=401,
                headers={'WWW-Authenticate': 'Bearer'})(scope, receive, send)
        handle = credential.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            credential.reset(handle)


application = AuthenticatedMCP(mcp.streamable_http_app())
