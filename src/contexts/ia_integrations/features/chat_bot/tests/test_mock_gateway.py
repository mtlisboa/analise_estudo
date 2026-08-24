from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from contexts.ia_integrations.features.chat_bot.application.contracts import ChatRequest
from contexts.ia_integrations.features.chat_bot.infrastructure.mock_agent_gateway import (
    MockAgentGateway,
)


class MockAgentGatewayTests(SimpleTestCase):
    def test_returns_deterministic_response_without_external_service(self):
        response = async_to_sync(MockAgentGateway().ask)(
            ChatRequest(message="Quero um diagnóstico", conversation_id="demo-1", user_id="1")
        )

        self.assertIn("diagnóstico demonstrativo", response.message)
        self.assertEqual(response.conversation_id, "demo-1")
        self.assertEqual(response.metadata["source"], "mock")
