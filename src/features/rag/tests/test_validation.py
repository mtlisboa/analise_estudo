import asyncio
import json
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
import httpx
from django.test import SimpleTestCase, override_settings
from django.urls import reverse, resolve
from features.rag.validation import validate_text, validate_output, validate_grounding
from features.rag.exceptions import InvalidGeneration
from features.rag.contracts import ChatRequest
from features.rag.orchestrator import AssistantGateway
from features.rag.infrastructure.knowledge import FileKnowledge
from features.rag.infrastructure.providers.ollama import acomplete

LOOP = '\n'.join(f'{i}. Clique em "Adicionar a atividade" para adicionar a atividade ao seu histórico de atividades.' for i in range(1, 74))


class TextValidationTests(TestCase):
    def test_reported_73_steps_are_rejected(self):
        with self.assertRaises(InvalidGeneration):
            validate_text(LOOP)

    def test_small_variations_and_unpunctuated_loop_are_rejected(self):
        for text in ('\n'.join(f'{i}. Clique no botão para adicionar a atividade ao histórico da turma {i}.' for i in range(1, 8)),
                     ('Clique em adicionar a atividade para adicionar esta atividade ao seu histórico de atividades ' * 6)):
            with self.assertRaises(InvalidGeneration):
                validate_text(text)

    def test_distinct_steps_and_shared_question_context_remain_valid(self):
        validate_text('1. Clique em Criar questionário para abrir o formulário.\n2. Clique em Selecionar questões para escolher os itens.\n3. Clique em Salvar questionário para concluir a edição.')
        validate_output({'questions':[{'support_text':'Leia o texto e responda à questão proposta.', 'statement':f'Qual é o resultado de {i}+1?'} for i in range(10)]})

    def test_unverified_step_is_not_accepted_even_without_repetition(self):
        with self.assertRaises(InvalidGeneration):
            validate_grounding('Clique em Adicionar a atividade ao histórico.', [{'text':'Clique em Salvar questionário.'}])
        validate_grounding('Clique em Salvar questionário.', [{'text':'Clique em Salvar questionário.'}])
        with self.assertRaises(InvalidGeneration):
            validate_grounding('Publique a atividade.', [{'text':'Não publique a atividade.'}])
        with self.assertRaises(InvalidGeneration):
            validate_grounding('Salve o questionário. Selecione questões.', [{'text':'Selecione questões. Salve o questionário.'}])


class Repository:
    async def context(self, user_id):
        return {'user_id':user_id}


class Provider:
    name = 'test'
    def __init__(self, result):
        self.acomplete = AsyncMock(return_value=result)


class OrchestratorValidationTests(IsolatedAsyncioTestCase):
    async def test_operational_loop_is_replaced_by_identified_manual_not_trimmed(self):
        provider = Provider(LOOP)
        reply = await AssistantGateway(provider, Repository(), FileKnowledge()).ask(
            ChatRequest('Como criar uma atividade?', 'c', 'u'))
        self.assertEqual(reply.metadata['source'], 'documentation')
        self.assertIn('Consulta direta ao manual', reply.message)
        self.assertIn('Salvar questionário', reply.message)
        self.assertNotIn('Adicionar a atividade', reply.message)
        self.assertEqual(reply.metadata['url'], '/avaliacoes/questionarios/novo/')
        self.assertEqual(provider.acomplete.await_count, 1)

    async def test_repetitive_question_proposal_never_reaches_repository_validation(self):
        repository = Repository()
        repository.validate = AsyncMock()
        provider = Provider({'message':'Revise a questão.', 'proposal':{'question':{'statement':LOOP}}})
        with self.assertRaises(InvalidGeneration):
            await AssistantGateway(provider, repository, FileKnowledge()).ask(ChatRequest('Crie uma questão', 'c', 'u', mode='assembly'))
        repository.validate.assert_not_called()

    async def test_invented_buttons_do_not_stream_and_are_not_preserved(self):
        provider = Provider('Clique em Adicionar a atividade ao histórico.')
        async def generate(*args, **kwargs):
            await kwargs['on_partial']('Clique em Adicionar a atividade ao histórico.')
            return 'Clique em Adicionar a atividade ao histórico.'
        provider.acomplete.side_effect = generate
        partial = AsyncMock()
        reply = await AssistantGateway(provider, Repository(), FileKnowledge()).ask(
            ChatRequest('Como criar uma atividade?', 'c', 'u', on_partial=partial))
        self.assertNotIn('Adicionar a atividade', reply.message)
        self.assertTrue(all(call.args == ('',) for call in partial.call_args_list))


@override_settings(OLLAMA_BASE_URL='http://ollama:11434', OLLAMA_TIMEOUT_SECONDS=2)
class StreamValidationTests(SimpleTestCase):
    async def test_repetition_closes_transport_before_done_or_hanging_tail(self):
        class Stream(httpx.AsyncByteStream):
            closed = False
            tail_reached = False
            async def __aiter__(self):
                yield (json.dumps({'message':{'content':LOOP}})+'\n').encode()
                self.tail_reached = True
                await asyncio.sleep(10)
            async def aclose(self):
                self.closed = True
        stream = Stream()
        factory = httpx.AsyncClient
        with patch('features.rag.infrastructure.providers.ollama.httpx.AsyncClient', side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)), **kwargs)):
            with self.assertRaises(InvalidGeneration):
                await acomplete([], structured=False)
        self.assertTrue(stream.closed)
        self.assertFalse(stream.tail_reached)

    def test_documentation_links_match_application_routes(self):
        self.assertEqual(reverse('assessments:questionnaire-create'), '/avaliacoes/questionarios/novo/')
        self.assertEqual(resolve('/avaliacoes/questoes/').url_name, 'question-bank')
