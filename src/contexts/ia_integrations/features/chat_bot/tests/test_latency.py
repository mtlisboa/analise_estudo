import asyncio
import json
from unittest.mock import AsyncMock, patch
import httpx
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from ..application.contracts import ChatRequest
from ..infrastructure.assistant_gateway import AssistantGateway, compact_result
from ..infrastructure.ollama_gateway import acomplete, partial_message
from ..application.exceptions import AgentUnavailable


class LazyContextTests(TransactionTestCase):
    async def test_greeting_does_not_query_reports_or_catalog(self):
        user = await get_user_model().objects.acreate_user(username='minimal')
        with patch('contexts.ia_integrations.features.chat_bot.application.context.user_context', side_effect=AssertionError('Eager data loading')), patch('contexts.institutions.analysis.services.build', side_effect=AssertionError('Eager report')), patch('contexts.ia_integrations.features.chat_bot.infrastructure.assistant_gateway.acomplete', new_callable=AsyncMock, return_value={'message':'Olá!', 'proposal':None}) as provider:
            result = await AssistantGateway().ask(ChatRequest('Oi', 'c', str(user.pk)))
        self.assertEqual(result.message, 'Olá!')
        prompt = provider.call_args.args[0]
        self.assertLess(sum(len(m['content']) for m in prompt), 4000)
        self.assertNotIn('data', result.metadata)

    def test_tool_data_is_bounded_json(self):
        result = compact_result({'rows':[{'text':'a'*20000} for _ in range(500)]})
        self.assertLessEqual(len(result), 4000)
        self.assertIn('limits', json.loads(result))


class Stream(httpx.AsyncByteStream):
    def __init__(self, lines, hang=False):
        self.lines = lines
        self.closed = False
        self.hang = hang
    async def __aiter__(self):
        for line in self.lines:
            yield (json.dumps(line)+'\n').encode()
        if self.hang:
            await asyncio.sleep(30)
    async def aclose(self):
        self.closed = True


@override_settings(OLLAMA_BASE_URL='http://ollama:11434', OLLAMA_TIMEOUT_SECONDS=5, OLLAMA_KEEP_ALIVE='30m')
class StreamingTests(SimpleTestCase):
    def client_patch(self, stream):
        factory = httpx.AsyncClient
        self.requests = []
        def handle(request):
            self.requests.append(request)
            return httpx.Response(200, stream=stream)
        return patch('contexts.ia_integrations.features.chat_bot.infrastructure.ollama_gateway.httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handle), **kw))

    async def test_stream_delivers_partial_text_and_validates_final_object(self):
        stream = Stream([{'message':{'content':'{"message":"Olá'}}, {'message':{'content':' mundo","proposal":null}'},'done':True}])
        callback = AsyncMock()
        with self.client_patch(stream):
            result = await acomplete([], structured=True, on_partial=callback)
        self.assertEqual(result['message'], 'Olá mundo')
        self.assertEqual(callback.call_args_list[0].args, ('Olá',))
        self.assertTrue(stream.closed)
        payload = json.loads(self.requests[0].content)
        self.assertTrue(payload['stream'])
        self.assertEqual(payload['keep_alive'], '30m')
        self.assertEqual(payload['options']['num_ctx'], 8192)

    async def test_cancellation_closes_provider_connection(self):
        stream = Stream([], hang=True)
        with self.client_patch(stream):
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(.03):
                    await acomplete([], structured=True)
        self.assertTrue(stream.closed)

    async def test_incomplete_stream_is_not_success(self):
        stream = Stream([{'message':{'content':'{"message":"incompleta'}}])
        with self.client_patch(stream), self.assertRaises(AgentUnavailable):
            await acomplete([], structured=True)

    def test_partial_parser_hides_json_and_handles_escapes(self):
        self.assertEqual(partial_message('{"tool":{"name":"analysis"}}'), '')
        self.assertEqual(partial_message('{"message":"linha\\ntexto'), 'linha\ntexto')
        self.assertEqual(partial_message('{"message":"ol\\u00'), 'ol')
