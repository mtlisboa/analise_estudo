import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TransactionTestCase, SimpleTestCase, override_settings
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP, Context
from features.assessments.models import QuestionBankItem
from features.rag.infrastructure.auth import issue_token, resolve_token
from features.rag.exceptions import AgentUnavailable
from features.rag.bootstrap import acomplete
from features.rag.presentation.mcp_server import mcp, application


@override_settings(ALLOWED_HOSTS=['testserver'])
class QuestionsMCPTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='mcp-owner')
        self.other = get_user_model().objects.create_user(username='mcp-other')
        self.question = QuestionBankItem.objects.create(owner=self.user, subject='Math', topic='Sum',
            statement='2+2?', question_type='multiple_choice', options=['4','5'], correct_answer='4')
        self.private = QuestionBankItem.objects.create(owner=self.other, subject='Secret', topic='Private', statement='Secret text')
        self.token = issue_token(self.user)

    def test_token_expiry_tampering_and_revocation(self):
        with patch('django.core.signing.time.time', return_value=1):
            expired = issue_token(self.user)
        for token in (expired, self.token+'tampered'):
            with self.assertRaises(PermissionDenied):
                resolve_token(token)
        self.user.set_password('changed'); self.user.save()
        with self.assertRaises(PermissionDenied):
            resolve_token(self.token)

    async def test_endpoint_rejects_missing_credentials_host_and_browser_origin(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://testserver') as client:
            self.assertEqual((await client.post('/mcp/questions')).status_code, 401)
            self.assertEqual((await client.post('/mcp/questions', headers={'Host':'evil.test'})).status_code, 400)
            self.assertEqual((await client.post('/mcp/questions', headers={'Authorization':'Bearer '+self.token, 'Origin':'http://testserver'})).status_code, 403)

    async def test_real_protocol_tools_scoping_no_writes_and_revalidation(self):
        async with mcp.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), headers={'Authorization':'Bearer '+self.token}) as http:
                async with streamable_http_client('http://testserver/mcp/questions', http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        self.assertEqual({t.name for t in listed.tools}, {'search_questions','get_question','get_questionnaire'})
                        result = await session.call_tool('search_questions', {})
                        self.assertFalse(result.isError)
                        rows = result.structuredContent['questions']
                        self.assertEqual([r['id'] for r in rows], [self.question.pk])
                        result = await session.call_tool('get_question', {'question_id': self.question.pk})
                        self.assertEqual(result.structuredContent['correct_answer'], '4')
                        denied = await session.call_tool('get_question', {'question_id': self.private.pk})
                        self.assertTrue(denied.isError)
                        self.assertNotIn('Secret text', str(denied))
                        unknown = await session.call_tool('edit_question', {'question_id': self.question.pk})
                        self.assertTrue(unknown.isError)
        self.assertEqual(await QuestionBankItem.objects.acount(), 2)
        self.user.is_active = False
        await database_sync_to_async(self.user.save)()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application)) as http:
            response = await http.post('http://testserver/mcp/questions', headers={'Authorization':'Bearer '+self.token})
            self.assertEqual(response.status_code, 401)


@override_settings(RAG_PROVIDER='mcp', RAG_MCP_URL='http://remote/mcp', RAG_MCP_TOOL='complete',
                   RAG_MCP_TOKEN='service-secret', RAG_MCP_TIMEOUT_SECONDS=2, RAG_QUESTIONS_MCP_URL='')
class RemoteProviderTests(TransactionTestCase):
    async def test_real_mcp_completion_and_shared_assessment_entrypoint(self):
        remote = FastMCP('Remote Test', host='0.0.0.0', stateless_http=True, json_response=True)
        calls = []
        @remote.tool()
        async def complete(messages: list[dict], structured: bool, ctx: Context) -> dict[str, Any]:
            calls.append((messages, structured, ctx.request_context.request.headers.get('authorization'), ctx.request_context.meta.model_dump() if ctx.request_context.meta else {}))
            return {'message': 'Resposta remota', 'proposal': None}
        app = remote.streamable_http_app()
        factory = httpx.AsyncClient
        with patch('features.rag.infrastructure.providers.mcp.httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.ASGITransport(app=app), **kw)):
            async with remote.session_manager.run():
                result = await acomplete([{'role':'user','content':'Oi'}], structured=True)
        self.assertEqual(result['message'], 'Resposta remota')
        self.assertEqual(calls[0][:3], ([{'role':'user','content':'Oi'}], True, 'Bearer service-secret'))
        from features.assessments.services import request_ai_json
        with patch('features.rag.bootstrap.acomplete', new_callable=AsyncMock, return_value={'question_ids':[1]}) as invoke:
            response = await database_sync_to_async(request_ai_json)('Selecione', 17)
        self.assertEqual(response, {'question_ids':[1]})
        self.assertEqual(invoke.call_args.kwargs['user_id'], 17)


    @override_settings(RAG_QUESTIONS_MCP_URL='https://school.example/mcp/questions')
    async def test_capability_is_bound_to_actor_and_kept_out_of_model_messages(self):
        user = await get_user_model().objects.acreate_user(username='remote-actor')
        remote = FastMCP('Capability Test', host='0.0.0.0', stateless_http=True, json_response=True)
        seen = []
        @remote.tool()
        async def complete(messages: list[dict], structured: bool, ctx: Context) -> dict[str, Any]:
            capability = ctx.request_context.meta.model_dump()['lumini/questions']
            actor = await database_sync_to_async(resolve_token)(capability['bearer_token'])
            seen.append(actor.pk)
            self.assertEqual(capability['url'], 'https://school.example/mcp/questions')
            self.assertNotIn(capability['bearer_token'], json.dumps(messages))
            return {'message':'ok', 'proposal':None}
        app = remote.streamable_http_app()
        factory = httpx.AsyncClient
        with patch('features.rag.infrastructure.providers.mcp.httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.ASGITransport(app=app), **kw)):
            async with remote.session_manager.run():
                result = await acomplete([{'role':'user','content':'Oi'}], structured=True, user_id=user.pk)
        self.assertEqual(result['message'], 'ok')
        self.assertEqual(seen, [user.pk])

    async def test_timeout_and_cancellation_propagate_without_fallback(self):
        async def hang(*args, **kw):
            await asyncio.sleep(10)
        with patch('features.rag.bootstrap.token_for', side_effect=hang), override_settings(RAG_QUESTIONS_MCP_URL='https://app/mcp/questions', RAG_MCP_TIMEOUT_SECONDS=.02):
            with self.assertRaises(AgentUnavailable):
                await acomplete([], structured=True, user_id=1)
            with self.assertRaises(asyncio.CancelledError):
                task = asyncio.create_task(acomplete([], structured=True, user_id=1))
                await asyncio.sleep(0)
                task.cancel()
                await task

    @override_settings(RAG_PROVIDER='unknown')
    async def test_unknown_provider_fails_closed(self):
        with self.assertRaises(AgentUnavailable):
            await acomplete([])
