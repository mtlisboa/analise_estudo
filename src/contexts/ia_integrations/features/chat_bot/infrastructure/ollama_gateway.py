"""Local inference; no fabricated fallback when the model is unavailable."""
import asyncio
import json
import urllib.error
import urllib.request

from django.conf import settings
from ..application.exceptions import AgentUnavailable


def complete(messages, *, structured=False):
    payload = {'model': settings.OLLAMA_MODEL, 'messages': messages, 'stream': False,
               'options': {'temperature': 0.2, 'num_ctx': 16384, 'num_predict': 4096}}
    if structured:
        payload['format'] = 'json'
    request = urllib.request.Request(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/chat',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=settings.OLLAMA_TIMEOUT_SECONDS) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError('Oversized response')
        result = json.loads(raw)
        text = result['message']['content']
        if not isinstance(text, str) or not text.strip() or result.get('done_reason') == 'length':
            raise ValueError('Empty or truncated response')
        if structured:
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError('Expected object')
            return result
        return text.strip()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AgentUnavailable('Não foi possível obter uma resposta válida do modelo. Verifique o Ollama e o download do modelo.') from exc


async def acomplete(messages, *, structured=False):
    return await asyncio.to_thread(complete, messages, structured=structured)
