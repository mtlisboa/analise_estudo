import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from django.test import TestCase, SimpleTestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from ..application.actions import validate_proposal, execute_proposal, question_payload
from ..application.context import user_context, read_tool, documentation
from ..application.exceptions import AgentUnavailable
from ..infrastructure.ollama_gateway import complete
from features.assessments.models import QuestionBankItem, Assessment, AssessmentTechnique
from features.assessments.services import request_ai_json

QUESTION = {'statement': 'Quanto é 2 + 2?', 'question_type': 'multiple_choice',
            'options': ['4', '5'], 'correct_answer': '4', 'explanation': 'Soma.', 'points': 1}


@override_settings(OLLAMA_BASE_URL='http://ollama:11434', OLLAMA_MODEL='test-model', OLLAMA_TIMEOUT_SECONDS=12)
class GatewayTests(SimpleTestCase):
    @patch('urllib.request.urlopen')
    def test_real_http_contract_structured(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({'message': {'content': json.dumps(QUESTION)}, 'done_reason': 'stop'}).encode()
        urlopen.return_value.__enter__.return_value = response
        self.assertEqual(request_ai_json('Crie uma questão', 1), QUESTION)
        req = urlopen.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, 'http://ollama:11434/api/chat')
        self.assertEqual(body['model'], 'test-model')
        self.assertFalse(body['stream'])
        self.assertEqual(body['format'], 'json')
        self.assertEqual(urlopen.call_args.kwargs['timeout'], 12)

    @patch('urllib.request.urlopen', side_effect=URLError('offline'))
    def test_no_fake_success_when_offline(self, _):
        with self.assertRaises(AgentUnavailable):
            complete([{'role': 'user', 'content': 'oi'}])

    @patch('urllib.request.urlopen')
    def test_rejects_truncation_and_invalid_json(self, urlopen):
        response = MagicMock()
        urlopen.return_value.__enter__.return_value = response
        for raw in [b'invalid', b'{"message":{"content":"{}"},"done_reason":"length"}', b'{"message":{"content":"[]"}}']:
            response.read.return_value = raw
            with self.assertRaises(AgentUnavailable):
                complete([], structured=True)


class ApplicationActionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='author')
        self.other = get_user_model().objects.create_user(username='other')
        self.technique = AssessmentTechnique.objects.create(code='assistant-test', name='Teste')
        self.source = QuestionBankItem.objects.create(owner=self.user, subject='Matemática', topic='Soma', **{k:v for k,v in QUESTION.items() if k != 'points'})
        self.private = QuestionBankItem.objects.create(owner=self.other, subject='Segredo', topic='Privado', **{k:v for k,v in QUESTION.items() if k != 'points'})

    def proposal(self, **kw):
        return dict(action='create_questionnaire', subject='Matemática', topic='Revisão', questions=[QUESTION], question_ids=[self.source.pk], **kw)

    def test_create_activity_from_generated_and_existing_questions(self):
        result = execute_proposal(self.user, self.proposal())
        a = Assessment.objects.get(owner=self.user)
        self.assertFalse(a.is_visible)
        self.assertEqual(a.questions.count(), 2)
        self.assertEqual(list(a.questions.values_list('order', flat=True)), [1, 2])
        self.assertIn(str(a.pk), result['url'])

    def test_preview_has_no_writes_and_ignores_model_owner(self):
        data = validate_proposal(self.user, {'action': 'create_question', 'owner_id': self.other.pk, 'subject': 'Math', 'topic': 'Sum', 'question': QUESTION})
        self.assertEqual(QuestionBankItem.objects.count(), 2)
        execute_proposal(self.user, data)
        self.assertEqual(QuestionBankItem.objects.filter(owner=self.user).count(), 2)

    def test_cannot_select_private_question(self):
        p = self.proposal(); p['question_ids'] = [self.private.pk]
        with self.assertRaises(ValidationError):
            execute_proposal(self.user, p)
        self.assertFalse(Assessment.objects.exists())

    def test_cannot_edit_other_author(self):
        with self.assertRaises(ValidationError):
            execute_proposal(self.user, {'action': 'edit_question', 'source_id': self.private.pk, 'question': QUESTION})

    def test_edit_creates_version_and_rejects_stale_proposal(self):
        p = validate_proposal(self.user, {'action': 'edit_question', 'source_id': self.source.pk, 'question': QUESTION})
        execute_proposal(self.user, p)
        self.assertEqual(QuestionBankItem.objects.filter(source_question=self.source).count(), 1)
        self.source.statement = 'Alterada'; self.source.save()
        with self.assertRaises(ValidationError):
            execute_proposal(self.user, p)

    def test_rollback_on_mid_save_failure(self):
        with patch('contexts.ia_integrations.features.chat_bot.application.actions._question_from_payload', side_effect=ValidationError('invalid')):
            with self.assertRaises(ValidationError):
                execute_proposal(self.user, self.proposal())
        self.assertFalse(Assessment.objects.exists())
        self.assertEqual(QuestionBankItem.objects.count(), 2)

    def test_reject_invalid_payloads(self):
        for value in ['NaN', 'Infinity', '-1', '0', '.001', '10000']:
            with self.assertRaises(ValidationError):
                question_payload(dict(QUESTION, points=value))
        for options in [['4', '4'], ['1', '2'], ['4'], '4']:
            with self.assertRaises(ValidationError):
                question_payload(dict(QUESTION, options=options))

    def test_no_cross_user_context_or_tools(self):
        data = user_context(self.user)
        self.assertEqual([q['id'] for q in data['questions']], [self.source.pk])
        self.assertNotIn('Segredo', json.dumps(data, default=str))
        self.assertEqual(read_tool(self.user, {'name': 'search_questions', 'query': 'Segredo'})['questions'], [])
        with self.assertRaises(ValidationError):
            read_tool(self.user, {'name': 'get_question', 'id': self.private.pk})
        with self.assertRaises(ValidationError):
            read_tool(self.user, {'name': 'execute_sql', 'sql': 'SELECT *'})

    def test_inactive_user_cannot_execute(self):
        self.user.is_active = False
        with self.assertRaises(ValidationError):
            execute_proposal(self.user, self.proposal())

    def test_documentation_has_sources(self):
        docs = documentation('Como interpretar as legendas e distratores?')
        self.assertTrue(docs)
        self.assertTrue(all(d['source'].startswith('Manual Lumini') for d in docs))

class InstitutionalContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from contexts.institutions.coursework.tests import CourseworkTests
        CourseworkTests.setUpTestData.__func__(cls)

    def test_teacher_and_manager_scope_reused_by_ai(self):
        from contexts.institutions.analysis.scope import Scope
        from contexts.institutions.analysis.services import build
        report = user_context(self.teacher.user)['institutional_analysis']
        self.assertEqual(report['metrics'], build(Scope(self.teacher.user), {})['metrics'])
        other = self.other.institutional_accounts.get(role='ADMIN').user
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(ValidationError):
            read_tool(other, {'name': 'analysis', 'filters': {'offer': self.offer.pk}})
        with self.assertRaises(ValidationError):
            read_tool(self.teacher.user, {'name': 'analysis', 'filters': {'subject': 'CIÊNCIAS'}})
        with self.assertRaises(PermissionDenied):
            read_tool(self.student.user, {'name': 'analysis', 'filters': {}})
        self.assertIsInstance(user_context(other)['institutional_analysis'], dict)

    def test_student_context_does_not_include_private_answers(self):
        self.assertNotIn('GABARITO PRIVADO', json.dumps(user_context(self.student.user), default=str))
        with self.assertRaises(ValidationError):
            read_tool(self.student.user, {'name': 'get_questionnaire', 'id': self.assessment.pk})

from django.test import TransactionTestCase
from unittest.mock import AsyncMock
from ..application.contracts import ChatRequest
from ..infrastructure.assistant_gateway import AssistantGateway


class AssistantPipelineTests(TransactionTestCase):
    async def test_context_retrieval_generation_and_proposal_without_saving(self):
        user = await get_user_model().objects.acreate_user(username='pipeline')
        source = await QuestionBankItem.objects.acreate(owner=user, subject='Math', topic='Sum', **{k:v for k,v in QUESTION.items() if k != 'points'})
        responses = [
            {'tool': {'name': 'get_question', 'id': source.pk}},
            {'message': 'Revise esta nova versão.', 'proposal': {'action':'edit_question', 'source_id':source.pk,'question':QUESTION}},
        ]
        with patch('contexts.ia_integrations.features.chat_bot.infrastructure.assistant_gateway.acomplete', new_callable=AsyncMock, side_effect=responses) as provider:
            result = await AssistantGateway().ask(ChatRequest('Edite minha questão', 'thread', str(user.pk), mode='assembly'))
        self.assertEqual(provider.await_count, 2)
        self.assertEqual(result.metadata['proposal']['source_id'], source.pk)
        self.assertEqual(result.metadata['sources'], [])
        self.assertEqual(result.metadata['consultations'][0]['result']['correct_answer'], '4')
        self.assertEqual(await QuestionBankItem.objects.acount(), 1)
        json.dumps(result.metadata)

    async def test_plain_reply_preserves_history_and_never_saves(self):
        user = await get_user_model().objects.acreate_user(username='plain-pipeline')
        history = ({'role':'user', 'content':'Explique frações', 'mode':'doubts'}, {'role':'assistant', 'content':'Uma parte do todo.', 'mode':'doubts'})
        with patch('contexts.ia_integrations.features.chat_bot.infrastructure.assistant_gateway.acomplete', new_callable=AsyncMock, return_value={'message':'Exercício: represente meio.', 'proposal':None}) as provider:
            result = await AssistantGateway().ask(ChatRequest('Crie exercício aqui na conversa', 'thread', str(user.pk), history))
        self.assertIn({'role':'user', 'content':'Explique frações'}, provider.call_args.args[0])
        self.assertNotIn('proposal', result.metadata)
        self.assertEqual(await QuestionBankItem.objects.acount(), 0)

    async def test_invalid_write_rejected_in_gateway(self):
        user = await get_user_model().objects.acreate_user(username='bad-pipeline')
        with patch('contexts.ia_integrations.features.chat_bot.infrastructure.assistant_gateway.acomplete', new_callable=AsyncMock, return_value={'message':'Proposta', 'proposal':{'action':'delete_all'}}):
            result = await AssistantGateway().ask(ChatRequest('Teste', 'thread', str(user.pk), mode='assembly'))
        self.assertNotIn('proposal', result.metadata)
        self.assertIn('Nenhuma alteração', result.message)
