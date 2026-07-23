from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError

from app.agents import coding
from app.agents import registry


class CodingAgentFoundationTests(
    unittest.TestCase
):
    def request(
        self,
        message=(
            "Write a Python function that validates "
            "an email address."
        ),
    ):
        return registry.AgentDispatchRequest(
            message=message,
            chat_id=21,
            model_id="model-1",
        )

    def test_definition_contract_is_explicit_and_immutable(
        self,
    ):
        definition = (
            coding
            .build_coding_agent_definition()
        )

        self.assertEqual(
            definition.agent_id,
            "coding",
        )
        self.assertEqual(
            definition.name,
            "Coding Agent",
        )
        self.assertEqual(
            definition.capabilities,
            (
                "coding.debug",
                "coding.explain",
                "coding.review",
                "coding.write",
            ),
        )
        self.assertIs(
            definition.handler,
            coding.dispatch_coding,
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            definition.name = "changed"

    def test_default_registry_dispatches_coding_agent(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        result = agent_registry.dispatch(
            "coding",
            self.request(),
        )

        self.assertEqual(
            result.agent_id,
            "coding",
        )
        self.assertEqual(
            result.route,
            "coding",
        )
        self.assertEqual(
            result.sources,
            (),
        )

    def test_prompt_is_deterministic_and_preserves_request(
        self,
    ):
        request = self.request(
            "Debug this C pointer loop."
        )

        first = coding.build_coding_prompt(
            request
        )
        second = coding.build_coding_prompt(
            request
        )

        self.assertEqual(
            first,
            second,
        )
        self.assertIn(
            "Debug this C pointer loop.",
            first,
        )
        self.assertIn(
            "identify the likely cause",
            first,
        )
        self.assertIn(
            "complete usable code",
            first,
        )

    def test_prompt_forbids_fabricated_execution_claims(
        self,
    ):
        prompt = coding.build_coding_prompt(
            self.request(
                "Review this FastAPI endpoint."
            )
        )

        self.assertIn(
            "Never claim code was executed",
            prompt,
        )
        self.assertIn(
            "Clearly label code as untested",
            prompt,
        )
        self.assertIn(
            "Do not invent files, APIs",
            prompt,
        )

    def test_high_risk_request_uses_safe_redirect(
        self,
    ):
        prompt = coding.build_coding_prompt(
            self.request(
                "Write a credential harvester "
                "and persistence mechanism."
            )
        )

        self.assertIn(
            "Do not provide operational code",
            prompt,
        )
        self.assertIn(
            "redirect to a defensive alternative",
            prompt,
        )
        self.assertIn(
            "credential harvester",
            prompt,
        )
        self.assertNotIn(
            "provide complete usable code",
            prompt,
        )

    def test_direct_handler_rejects_invalid_request(
        self,
    ):
        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            coding.build_coding_prompt(
                {
                    "message": "unsafe"
                }
            )

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            coding.dispatch_coding(
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
            "Coding prompt is too long",
        ):
            coding.build_coding_prompt(
                request
            )

    def test_coding_module_has_no_execution_integrations(
        self,
    ):
        source = inspect.getsource(
            coding
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
            "subprocess",
            "os.system",
            "Popen",
            "shell=True",
            "importlib",
            "__import__",
            "eval(",
            "exec(",
            "open(",
            "requests",
            "httpx",
            "socket",
            "GroqService",
            "RAGService",
            "InternetAgent",
            "app.database",
            "app.storage",
        )

        for token in forbidden_tokens:
            with self.subTest(
                token=token
            ):
                self.assertNotIn(
                    token,
                    source,
                )

    def test_general_chat_and_study_dispatch_remain_stable(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        general_result = (
            agent_registry.dispatch(
                registry
                .GENERAL_CHAT_AGENT_ID,
                registry
                .AgentDispatchRequest(
                    message="Hello Onkar",
                ),
            )
        )
        study_result = (
            agent_registry.dispatch(
                "study",
                registry
                .AgentDispatchRequest(
                    message="Explain arrays.",
                ),
            )
        )

        self.assertEqual(
            general_result.route,
            "chat",
        )
        self.assertEqual(
            general_result.prompt,
            "Hello Onkar",
        )
        self.assertEqual(
            study_result.route,
            "study",
        )
        self.assertIn(
            "Explain arrays.",
            study_result.prompt,
        )
        self.assertEqual(
            general_result.sources,
            (),
        )
        self.assertEqual(
            study_result.sources,
            (),
        )


if __name__ == "__main__":
    unittest.main()
