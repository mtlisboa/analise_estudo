from unittest.mock import AsyncMock, patch
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from contexts.ia_integrations.rag.contracts import ChatRequest
from contexts.ia_integrations.rag.orchestrator import AssistantGateway, COMMON, DOUBTS, ASSEMBLY
from contexts.ia_integrations.rag.exceptions import AgentUnavailable


class ModeTests(TransactionTestCase):
    async def test_doubts_uses_smaller_prompt_and_only_its_history(self):
        user = await get_user_model().objects.acreate_user(username='modes')
        history = ({'role':'user', 'content':'SEGREDO DA MONTAGEM', 'mode':'assembly'},
                   {'role':'user', 'content':'Explique frações', 'mode':'doubts'})
        with patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value='Uma fração representa uma parte de um todo.') as provider:
            await AssistantGateway().ask(ChatRequest('Uma dúvida', 'c', str(user.pk), history, mode='doubts'))
        prompt = str(provider.call_args.args[0])
        self.assertNotIn('SEGREDO DA MONTAGEM', prompt)
        self.assertNotIn('create_questionnaire', prompt)
        self.assertIn('Explique frações', prompt)
        self.assertFalse(provider.call_args.kwargs['allow_question_tools'])
        self.assertLess(len(COMMON + DOUBTS), len(COMMON + ASSEMBLY) / 2)

    async def test_assembly_skips_manual_and_analysis_instructions(self):
        user = await get_user_model().objects.acreate_user(username='assembly')
        with patch('contexts.ia_integrations.rag.orchestrator.documentation', side_effect=AssertionError('Unused manual')),\
             patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value={'message':'Qual disciplina?'}) as provider:
            await AssistantGateway().ask(ChatRequest('Monte uma atividade', 'c', str(user.pk), mode='assembly'))
        prompt = str(provider.call_args.args[0])
        self.assertNotIn('analysis_options', prompt)
        self.assertIn('create_questionnaire', prompt)
        self.assertTrue(provider.call_args.kwargs['allow_question_tools'])

    async def test_disallowed_tools_and_proposals_do_not_execute_in_doubts(self):
        user = await get_user_model().objects.acreate_user(username='blocked')
        with patch('contexts.ia_integrations.rag.orchestrator.read_for', new_callable=AsyncMock) as read,\
             patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value={'tool':{'name':'search_questions'}}):
            with self.assertRaises(AgentUnavailable):
                await AssistantGateway().ask(ChatRequest('Busque', 'c', str(user.pk)))
            read.assert_not_called()
        with patch('contexts.ia_integrations.rag.orchestrator.validate_for', new_callable=AsyncMock) as validate,\
             patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value={'message':'Proposta', 'proposal':{'action':'create_question'}}):
            result = await AssistantGateway().ask(ChatRequest('Crie', 'c', str(user.pk)))
            self.assertNotIn('proposal', result.metadata)
            self.assertIn('Montagem', result.message)
            validate.assert_not_called()

    async def test_placeholder_is_repaired_once_without_reusing_example(self):
        user = await get_user_model().objects.acreate_user(username='repair')
        with patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   side_effect=['resposta', 'Abra Questionários, crie um questionário e selecione as questões.']) as provider:
            result = await AssistantGateway().ask(ChatRequest('como criar uma atividade', 'c', str(user.pk)))
        self.assertEqual(provider.await_count, 2)
        self.assertFalse(provider.call_args.kwargs['structured'])
        self.assertIn('selecione as questões', result.message)
        self.assertNotIn('data', result.metadata)
        self.assertEqual(result.metadata['sources'], ['Manual Lumini — Questionários e atividades'])

    async def test_repeated_placeholder_is_rejected(self):
        user = await get_user_model().objects.acreate_user(username='bad-answer')
        with patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value='resposta') as provider:
            with self.assertRaises(AgentUnavailable):
                await AssistantGateway().ask(ChatRequest('Como criar uma atividade?', 'c', str(user.pk)))
        self.assertEqual(provider.await_count, 2)

    async def test_analysis_uses_authorized_data_and_separate_history(self):
        user = await get_user_model().objects.acreate_user(username='analysis-mode')
        history = ({'role':'user', 'content':'QUESTAO ANTIGA', 'mode':'assembly'},)
        with patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   side_effect=[{'tool':{'name':'my_data'}}, {'message':'Você ainda não possui resultados revisados.'}]) as provider:
            result = await AssistantGateway().ask(ChatRequest('Interprete meus dados', 'c', str(user.pk), history, mode='analysis'))
        self.assertEqual(result.metadata['mode'], 'analysis')
        self.assertEqual(result.metadata['consultations'][0]['result']['results'], [])
        self.assertNotIn('QUESTAO ANTIGA', str(provider.call_args.args[0]))
        self.assertNotIn('create_questionnaire', str(provider.call_args.args[0]))
        self.assertFalse(provider.call_args.kwargs['allow_question_tools'])

    async def test_analysis_does_not_present_unqueried_numbers_as_facts(self):
        user = await get_user_model().objects.acreate_user(username='ungrounded')
        with patch('contexts.ia_integrations.rag.orchestrator.acomplete', new_callable=AsyncMock,
                   return_value={'message':'Sua média é 90%.'}):
            result = await AssistantGateway().ask(ChatRequest('Analise', 'c', str(user.pk), mode='analysis'))
        self.assertNotIn('90%', result.message)
        self.assertIn('Ainda não consultei', result.message)
