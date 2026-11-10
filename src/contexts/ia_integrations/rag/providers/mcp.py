"""Remote inference through an MCP completion tool, not an HTTP imitation of MCP."""
import asyncio
import json
from urllib.parse import urlsplit
import httpx
from django.conf import settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from ..auth import token_for
from ..exceptions import AgentUnavailable


async def acomplete(messages, *, structured=False, on_partial=None, user_id=None):
    endpoint = settings.RAG_MCP_URL
    if urlsplit(endpoint).scheme not in ('http', 'https') or not urlsplit(endpoint).hostname:
        raise AgentUnavailable('Configure RAG_MCP_URL para usar o provedor MCP.')
    headers = {'Authorization': 'Bearer ' + settings.RAG_MCP_TOKEN} if settings.RAG_MCP_TOKEN else {}
    try:
        async with asyncio.timeout(settings.RAG_MCP_TIMEOUT_SECONDS):
            # Credentials are transport metadata for the trusted service, never model messages.
            meta = None
            if settings.RAG_QUESTIONS_MCP_URL:
                meta = {'lumini/questions': {'url': settings.RAG_QUESTIONS_MCP_URL,
                        'bearer_token': await token_for(user_id), 'expires_in': 300}}
            async with httpx.AsyncClient(headers=headers, timeout=settings.RAG_MCP_TIMEOUT_SECONDS,
                                         follow_redirects=False) as http:
                async with streamable_http_client(endpoint, http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(settings.RAG_MCP_TOOL,
                            {'messages': messages, 'structured': structured}, meta=meta)
            if result.isError:
                raise ValueError('Remote tool failed')
            value = result.structuredContent
            if value is None:
                raw = ''.join(c.text for c in result.content if c.type == 'text')
                if len(raw) > 131072:
                    raise ValueError('Oversized result')
                value = json.loads(raw) if structured else raw
            if len(json.dumps(value)) > 131072 or (structured and not isinstance(value, dict)):
                raise ValueError('Invalid result')
            if not value:
                raise ValueError('Empty result')
            if on_partial and isinstance(value, dict) and isinstance(value.get('message'), str):
                await on_partial(value['message'])
            return value
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Do not expose endpoint credentials, remote exceptions or tokens to the browser.
        raise AgentUnavailable('O serviço MCP não respondeu corretamente ou excedeu o prazo configurado.') from exc
