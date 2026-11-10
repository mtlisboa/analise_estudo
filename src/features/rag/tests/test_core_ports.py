"""These tests run without Django setup, a database, or a network client."""
import ast
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from features.rag.contracts import ChatRequest
from features.rag.orchestrator import AssistantGateway


class FakeProvider:
    name = 'in-memory'
    def __init__(self):
        self.calls = 0
    async def acomplete(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {'tool': {'name': 'get_question', 'id': 7}}
        return {'message': 'Revise a nova versão antes de salvar.',
                'proposal': {'action': 'edit_question', 'source_id': 7}}


class FakeRepository:
    def __init__(self):
        self.reads = []
        self.validations = []
    async def context(self, user_id):
        return {'user_id': user_id}
    async def read(self, user_id, tool):
        self.reads.append((user_id, tool))
        return {'id':7, 'statement':'Quanto é 2+2?', 'correct_answer':'4'}
    async def validate(self, user_id, proposal):
        self.validations.append((user_id, proposal))
        return dict(proposal, version='v1')


class FakeKnowledge:
    def search(self, query):
        return []


class InjectedPortsTests(IsolatedAsyncioTestCase):
    async def test_orchestration_with_replaced_network_and_database(self):
        provider, repository = FakeProvider(), FakeRepository()
        gateway = AssistantGateway(provider, repository, FakeKnowledge())
        result = await gateway.ask(ChatRequest('Edite a questão 7', 'conversation', 'actor', mode='assembly'))
        self.assertEqual(provider.calls, 2)
        self.assertEqual(repository.reads, [('actor', {'name':'get_question', 'id':7})])
        self.assertEqual(repository.validations[0][0], 'actor')
        self.assertEqual(result.metadata['proposal']['version'], 'v1')
        self.assertEqual(result.metadata['source'], 'in-memory')


class DependencyBoundaryTests(TestCase):
    def test_core_does_not_import_database_or_network_implementations(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('orchestrator.py', 'ports.py', 'contracts.py', 'exceptions.py'):
            tree = ast.parse((root/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                else:
                    continue
                for module in modules:
                    self.assertFalse(any(x in module.split('.') for x in
                        ('django', 'channels', 'httpx', 'urllib', 'mcp', 'infrastructure', 'bootstrap', 'models')), (name, module))
