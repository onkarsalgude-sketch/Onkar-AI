from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError

from app.agents import registry
from app.agents import study


class StudyAgentFoundationTests(
    unittest.TestCase
):
    def request(
        self,
        message=(
            "Explain binary numbers for a beginner."
        ),
    ):
        return registry.AgentDispatchRequest(
            message=message,
            chat_id=11,
            model_id="model-1",
        )

    def test_definition_contract_is_explicit_and_immutable(
        self,
    ):
        definition = (
            study
            .build_study_agent_definition()
        )

        self.assertEqual(
            definition.agent_id,
            "study",
        )
        self.assertEqual(
            definition.name,
            "Study Agent",
        )
        self.assertEqual(
            definition.capabilities,
            (
                "study.explain",
                "study.quiz",
                "study.revise",
            ),
        )
        self.assertIs(
            definition.handler,
            study.dispatch_study,
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            definition.name = "changed"

    def test_default_registry_dispatches_study_agent(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )
        request = self.request()

        result = agent_registry.dispatch(
            "study",
            request,
        )

        self.assertEqual(
            result.agent_id,
            "study",
        )
        self.assertEqual(
            result.route,
            "study",
        )
        self.assertEqual(
            result.sources,
            (),
        )

    def test_prompt_is_deterministic_and_preserves_request(
        self,
    ):
        request = self.request(
            "Explain pointers with one example."
        )

        first = study.build_study_prompt(
            request
        )
        second = study.build_study_prompt(
            request
        )

        self.assertEqual(
            first,
            second,
        )
        self.assertIn(
            "Explain pointers with one example.",
            first,
        )
        self.assertIn(
            "level-appropriate",
            first,
        )
        self.assertIn(
            "step by step",
            first,
        )

    def test_prompt_contains_quiz_revision_and_source_rules(
        self,
    ):
        prompt = study.build_study_prompt(
            self.request(
                "Create a short quiz."
            )
        )

        self.assertIn(
            "do not reveal answers",
            prompt,
        )
        self.assertIn(
            "For revision requests",
            prompt,
        )
        self.assertIn(
            "Do not invent facts, sources, citations",
            prompt,
        )
        self.assertIn(
            "unless the student request actually provides one",
            prompt,
        )

    def test_direct_handler_rejects_invalid_request(
        self,
    ):
        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            study.build_study_prompt(
                {
                    "message": "unsafe"
                }
            )

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            study.dispatch_study(
                {
                    "message": "unsafe"
                }
            )

    def test_prompt_bound_rejects_oversized_result(
        self,
    ):
        request = (
            registry.AgentDispatchRequest(
                message=(
                    "x"
                    * (
                        registry
                        .MAX_AGENT_MESSAGE_LENGTH
                        - 10
                    )
                )
            )
        )

        with self.assertRaisesRegex(
            registry
            .AgentRegistryValidationError,
            "Study prompt is too long",
        ):
            study.build_study_prompt(
                request
            )

    def test_study_module_has_no_external_integration_imports(
        self,
    ):
        source = inspect.getsource(
            study
        )
        tree = ast.parse(source)
        imported_modules = set()

        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.Import,
            ):
                imported_modules.update(
                    alias.name
                    for alias in node.names
                )
            elif isinstance(
                node,
                ast.ImportFrom,
            ):
                imported_modules.add(
                    node.module or ""
                )

        self.assertEqual(
            imported_modules,
            {
                "__future__",
                "app.agents.registry",
            },
        )

        forbidden_tokens = (
            "GroqService",
            "RAGService",
            "retrieve_knowledge_context",
            "InternetAgent",
            "app.database",
            "app.storage",
            "importlib",
            "__import__",
            "eval(",
            "exec(",
        )

        for token in forbidden_tokens:
            with self.subTest(
                token=token
            ):
                self.assertNotIn(
                    token,
                    source,
                )

    def test_general_chat_dispatch_remains_unchanged(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )
        request = (
            registry.AgentDispatchRequest(
                message="Hello Onkar",
            )
        )

        result = agent_registry.dispatch(
            registry
            .GENERAL_CHAT_AGENT_ID,
            request,
        )

        self.assertEqual(
            result.agent_id,
            registry
            .GENERAL_CHAT_AGENT_ID,
        )
        self.assertEqual(
            result.route,
            "chat",
        )
        self.assertEqual(
            result.prompt,
            "Hello Onkar",
        )
        self.assertEqual(
            result.sources,
            (),
        )


if __name__ == "__main__":
    unittest.main()
