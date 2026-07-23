from __future__ import annotations

import inspect
import unittest
from unittest.mock import Mock, patch

from app.agents import brain as brain_module
from app.agents import registry
from app.agents import selection


class _FailingLayer:
    def __getattr__(self, name):
        raise AssertionError(
            "Automatic layer must not be used."
        )


class _FakeAI:
    def __init__(self):
        self.reply_calls = []
        self.stream_calls = []
        self.build_calls = []
        self.resolved_models = []

    def generate_reply(
        self,
        message,
        model_id=None,
    ):
        self.reply_calls.append(
            (message, model_id)
        )
        return "generated reply"

    def generate_reply_stream(
        self,
        prompt,
        model_id=None,
    ):
        self.stream_calls.append(
            (prompt, model_id)
        )
        return iter(
            (
                "chunk-1",
                "chunk-2",
            )
        )

    def build_prompt(self, message):
        self.build_calls.append(message)
        return "built:" + message

    def resolve_model(self, model_id=None):
        self.resolved_models.append(
            model_id
        )
        return model_id or "default-model"


class BrainAgentDispatchIntegrationTests(
    unittest.TestCase
):
    def make_brain(
        self,
        *,
        agent_registry=None,
    ):
        instance = brain_module.Brain.__new__(
            brain_module.Brain
        )
        instance.rag = _FailingLayer()
        instance.ai = _FakeAI()
        instance.internet = _FailingLayer()
        instance.router = _FailingLayer()
        instance.agent_registry = (
            agent_registry
            or registry
            .build_default_agent_registry()
        )
        return instance

    def test_constructor_owns_default_registry(
        self,
    ):
        with (
            patch.object(
                brain_module,
                "RAGService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "GroqService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "InternetAgent",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "AgentRouter",
                return_value=Mock(),
            ),
        ):
            instance = brain_module.Brain()

        self.assertEqual(
            tuple(
                item["agent_id"]
                for item
                in instance
                .agent_registry
                .list_agents()
            ),
            (
                "coding",
                "document",
                "general-chat",
                "market-research",
                "study",
            ),
        )

    def test_constructor_accepts_registry_injection(
        self,
    ):
        injected = registry.AgentRegistry(
            (
                registry.AgentDefinition(
                    agent_id="safe-agent",
                    name="Safe Agent",
                    description=(
                        "Safe injected test agent."
                    ),
                    capabilities=(
                        "safe.respond",
                    ),
                    handler=lambda request: (
                        registry.AgentDispatchResult(
                            agent_id="safe-agent",
                            route="safe-agent",
                            prompt=request.message,
                            sources=(),
                        )
                    ),
                ),
            )
        )

        with (
            patch.object(
                brain_module,
                "RAGService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "GroqService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "InternetAgent",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "AgentRouter",
                return_value=Mock(),
            ),
        ):
            instance = brain_module.Brain(
                agent_registry=injected
            )

        self.assertIs(
            instance.agent_registry,
            injected,
        )

    def test_constructor_rejects_invalid_registry(
        self,
    ):
        with (
            patch.object(
                brain_module,
                "RAGService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "GroqService",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "InternetAgent",
                return_value=Mock(),
            ),
            patch.object(
                brain_module,
                "AgentRouter",
                return_value=Mock(),
            ),
            self.assertRaisesRegex(
                selection.AgentSelectionError,
                "^Unable to select agent[.]$",
            ),
        ):
            brain_module.Brain(
                agent_registry={}
            )

    def test_no_agent_normal_chat_contract_is_unchanged(
        self,
    ):
        instance = self.make_brain()
        instance.router = Mock()
        instance.router.route.return_value = (
            "chat"
        )

        with patch.object(
            brain_module,
            "retrieve_knowledge_context",
            return_value={
                "context": "",
                "sources": [],
            },
        ):
            prepared = instance.prepare_request(
                "Hello",
                chat_id=7,
                model_id="model-a",
            )

        self.assertEqual(
            prepared,
            {
                "route": "chat",
                "prompt": "Hello",
                "sources": [],
            },
        )
        instance.router.route.assert_called_once_with(
            "Hello"
        )

    def test_no_agent_internet_contract_is_unchanged(
        self,
    ):
        instance = self.make_brain()
        instance.router = Mock()
        instance.router.route.return_value = (
            "internet"
        )
        instance.internet = Mock()
        instance.internet.search.return_value = {
            "answer": "fresh result",
            "sources": [
                {
                    "title": "Source",
                    "url": "https://example.com",
                }
            ],
        }

        prepared = instance.prepare_request(
            "Search online",
            chat_id=7,
            model_id="model-a",
        )

        self.assertEqual(
            prepared["route"],
            "internet",
        )
        self.assertIn(
            "fresh result",
            prepared["prompt"],
        )
        self.assertEqual(
            prepared["sources"],
            [
                {
                    "title": "Source",
                    "url": "https://example.com",
                }
            ],
        )

    def test_explicit_general_chat_bypasses_automatic_layers(
        self,
    ):
        instance = self.make_brain()

        with patch.object(
            brain_module,
            "retrieve_knowledge_context",
            side_effect=AssertionError(
                "Knowledge must not run."
            ),
        ):
            prepared = instance.prepare_request(
                "Search online for this",
                chat_id=11,
                model_id="model-b",
                agent_id="general-chat",
            )

        self.assertEqual(
            prepared,
            {
                "agent_id": "general-chat",
                "route": "chat",
                "prompt": "Search online for this",
                "sources": [],
            },
        )

    def test_specialized_agents_bypass_automatic_layers(
        self,
    ):
        instance = self.make_brain()

        cases = (
            "coding",
            "document",
            "market-research",
            "study",
        )

        with patch.object(
            brain_module,
            "retrieve_knowledge_context",
            side_effect=AssertionError(
                "Knowledge must not run."
            ),
        ):
            for agent_id in cases:
                with self.subTest(
                    agent_id=agent_id
                ):
                    prepared = (
                        instance.prepare_request(
                            "Use this exact request.",
                            chat_id=12,
                            model_id="model-c",
                            agent_id=agent_id,
                        )
                    )

                    self.assertEqual(
                        prepared["agent_id"],
                        agent_id,
                    )
                    self.assertEqual(
                        prepared["route"],
                        agent_id,
                    )
                    self.assertIn(
                        "Use this exact request.",
                        prepared["prompt"],
                    )
                    self.assertEqual(
                        prepared["sources"],
                        [],
                    )

    def test_dispatch_request_preserves_fields(
        self,
    ):
        captured = []

        def handler(request):
            captured.append(request)
            return (
                registry.AgentDispatchResult(
                    agent_id="capture-agent",
                    route="capture-agent",
                    prompt="captured:"
                    + request.message,
                    sources=(),
                )
            )

        injected = registry.AgentRegistry(
            (
                registry.AgentDefinition(
                    agent_id="capture-agent",
                    name="Capture Agent",
                    description=(
                        "Captures dispatch fields."
                    ),
                    capabilities=(
                        "capture.respond",
                    ),
                    handler=handler,
                ),
            )
        )
        instance = self.make_brain(
            agent_registry=injected
        )

        prepared = instance.prepare_request(
            "Preserve me",
            chat_id=77,
            model_id="model-z",
            agent_id="capture-agent",
        )

        self.assertEqual(
            len(captured),
            1,
        )
        self.assertEqual(
            captured[0].message,
            "Preserve me",
        )
        self.assertEqual(
            captured[0].chat_id,
            77,
        )
        self.assertEqual(
            captured[0].model_id,
            "model-z",
        )
        self.assertEqual(
            prepared["prompt"],
            "captured:Preserve me",
        )

    def test_invalid_agent_fails_before_automatic_layers(
        self,
    ):
        instance = self.make_brain()

        with (
            patch.object(
                brain_module,
                "retrieve_knowledge_context",
                side_effect=AssertionError(
                    "Knowledge must not run."
                ),
            ),
            self.assertRaisesRegex(
                selection.AgentSelectionError,
                "^Unable to select agent[.]$",
            ),
        ):
            instance.prepare_request(
                "Hello",
                chat_id=2,
                model_id="model-a",
                agent_id="missing-agent",
            )

    def test_chat_uses_specialized_prompt_once(
        self,
    ):
        instance = self.make_brain()

        with patch.object(
            brain_module,
            "add",
        ) as add_mock:
            result = instance.chat(
                "Explain this code.",
                chat_id=5,
                model_id="model-d",
                agent_id="coding",
            )

        self.assertEqual(
            len(instance.ai.reply_calls),
            1,
        )
        sent_prompt, sent_model = (
            instance.ai.reply_calls[0]
        )
        self.assertIn(
            "Explain this code.",
            sent_prompt,
        )
        self.assertEqual(
            sent_model,
            "model-d",
        )
        self.assertEqual(
            result["agent_id"],
            "coding",
        )
        self.assertEqual(
            result["sources"],
            [],
        )
        self.assertEqual(
            add_mock.call_count,
            2,
        )

    def test_stream_uses_specialized_prompt_once(
        self,
    ):
        instance = self.make_brain()

        result = instance.stream_chat(
            "Rewrite this notice.",
            chat_id=6,
            model_id="model-e",
            agent_id="document",
        )

        self.assertEqual(
            len(instance.ai.stream_calls),
            1,
        )
        sent_prompt, sent_model = (
            instance.ai.stream_calls[0]
        )
        self.assertIn(
            "Rewrite this notice.",
            sent_prompt,
        )
        self.assertEqual(
            sent_model,
            "model-e",
        )
        self.assertEqual(
            instance.ai.build_calls,
            [],
        )
        self.assertEqual(
            result["agent_id"],
            "document",
        )
        self.assertEqual(
            tuple(result["stream"]),
            (
                "chunk-1",
                "chunk-2",
            ),
        )

    def test_no_agent_chat_generation_remains_raw(
        self,
    ):
        instance = self.make_brain()
        instance.router = Mock()
        instance.router.route.return_value = (
            "chat"
        )

        with (
            patch.object(
                brain_module,
                "retrieve_knowledge_context",
                return_value={
                    "context": "",
                    "sources": [],
                },
            ),
            patch.object(
                brain_module,
                "add",
            ),
        ):
            result = instance.chat(
                "Normal message",
                chat_id=1,
                model_id="model-f",
            )

        self.assertEqual(
            instance.ai.reply_calls,
            [
                (
                    "Normal message",
                    "model-f",
                )
            ],
        )
        self.assertNotIn(
            "agent_id",
            result,
        )

    def test_no_agent_stream_builds_normal_prompt(
        self,
    ):
        instance = self.make_brain()
        instance.router = Mock()
        instance.router.route.return_value = (
            "chat"
        )

        with patch.object(
            brain_module,
            "retrieve_knowledge_context",
            return_value={
                "context": "",
                "sources": [],
            },
        ):
            result = instance.stream_chat(
                "Normal stream",
                chat_id=1,
                model_id="model-g",
            )

        self.assertEqual(
            instance.ai.build_calls,
            [
                "Normal stream"
            ],
        )
        self.assertEqual(
            instance.ai.stream_calls,
            [
                (
                    "built:Normal stream",
                    "model-g",
                )
            ],
        )
        self.assertNotIn(
            "agent_id",
            result,
        )

    def test_public_signatures_append_agent_id(
        self,
    ):
        prepare = inspect.signature(
            brain_module.Brain.prepare_request
        )
        chat = inspect.signature(
            brain_module.Brain.chat
        )
        stream = inspect.signature(
            brain_module.Brain.stream_chat
        )

        self.assertEqual(
            tuple(prepare.parameters),
            (
                "self",
                "message",
                "chat_id",
                "model_id",
                "agent_id",
            ),
        )
        self.assertEqual(
            tuple(chat.parameters),
            (
                "self",
                "message",
                "chat_id",
                "model_id",
                "agent_id",
            ),
        )
        self.assertEqual(
            tuple(stream.parameters),
            (
                "self",
                "message",
                "chat_id",
                "model_id",
                "agent_id",
            ),
        )


if __name__ == "__main__":
    unittest.main()
