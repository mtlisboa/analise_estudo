"""Local inference; no fabricated fallback when the model is unavailable."""
import asyncio
import re
import time
import logging
import httpx
import json
import urllib.error
import urllib.request

from django.conf import settings
from ..application.exceptions import AgentUnavailable


def complete(messages, *, structured=False):
    payload = {'model': settings.OLLAMA_MODEL, 'messages': messages, 'stream': False,
               'keep_alive': settings.OLLAMA_KEEP_ALIVE,
               'options': {'temperature': 0.2, 'num_ctx': 8192, 'num_predict': 4096}}
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


def partial_message(content):
    # Emit only the message field, not raw JSON or proposed actions.
    match = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)', content)
    if not match:
        return ''
    value = match.group(1)
    for trim in range(min(7, len(value) + 1)):
        try:
            return json.loads('"' + (value[:-trim] if trim else value) + '"')
        except ValueError:
            pass
    return ''


async def acomplete(messages, *, structured=False, on_partial=None):
    payload = {'model': settings.OLLAMA_MODEL, 'messages': messages, 'stream': True,
        'keep_alive': settings.OLLAMA_KEEP_ALIVE,
        'options': {'temperature': 0.2, 'num_ctx': 8192, 'num_predict': 2048}}
    if structured:
        payload['format'] = 'json'
    text, last_sent = '', ''
    sent_at = 0
    started = time.monotonic()
    done = None
    try:
        async with asyncio.timeout(settings.OLLAMA_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.OLLAMA_TIMEOUT_SECONDS, connect=10)) as client:
                async with client.stream('POST', settings.OLLAMA_BASE_URL.rstrip('/') + '/api/chat', json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if len(line) > 262144:
                            raise ValueError('Oversized response')
                        chunk = json.loads(line)
                        if chunk.get('error'):
                            raise ValueError('Provider error')
                        text += chunk.get('message', {}).get('content', '')
                        if len(text) > 131072:
                            raise ValueError('Oversized response')
                        partial = partial_message(text) if structured else text
                        if on_partial and partial != last_sent and time.monotonic() - sent_at >= .15:
                            await on_partial(partial)
                            last_sent, sent_at = partial, time.monotonic()
                        if chunk.get('done'):
                            done = chunk
                            break
        if done is None or done.get('done_reason') == 'length' or not text.strip():
            raise ValueError('Incomplete response')
        result = json.loads(text) if structured else text
        if structured and not isinstance(result, dict):
            raise ValueError('Expected object')
        logging.getLogger(__name__).info('Ollama elapsed=%.2fs prompt_tokens=%s output_tokens=%s load_ns=%s',
            time.monotonic()-started, done.get('prompt_eval_count'), done.get('eval_count'), done.get('load_duration'))
        return result
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        logging.getLogger(__name__).warning('Ollama failure kind=%s elapsed=%.2fs', type(exc).__name__, time.monotonic()-started)
        raise AgentUnavailable('O modelo não concluiu uma resposta válida. Tente reduzir a quantidade de questões ou o contexto solicitado.') from exc
