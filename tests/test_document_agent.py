from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError

from app.agents import document
from app.agents import registry


class DocumentAgentFoundationTests(
    unittest.TestCase
):
    def request(
        self,
        message=(
            "Draft a professional resume summary "
            "for Onkar Haribhau Salgude."
        ),
    ):
        return registry.AgentDispatchRequest(
            message=message,
            chat_id=31,
            model_id="model-1",
        )

    def test_definition_contract_is_explicit_and_immutable(
        self,
    ):
        definition = (
            document
            .build_document_agent_definition()
        )

        self.assertEqual(
            definition.agent_id,
            "document",
        )
        self.assertEqual(
            definition.name,
            "Document Agent",
        )
        self.assertEqual(
            definition.capabilities,
            (
                "document.draft",
                "document.resume",
                "document.rewrite",
                "document.summarize",
            ),
        )
        self.assertIs(
            definition.handler,
            document.dispatch_document,
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            definition.name = "changed"

    def test_default_registry_dispatches_document_agent(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        result = agent_registry.dispatch(
            "document",
            self.request(),
        )

        self.assertEqual(
            result.agent_id,
            "document",
        )
        self.assertEqual(
            result.route,
            "document",
        )
        self.assertEqual(
            result.sources,
            (),
        )

    def test_prompt_is_deterministic_and_preserves_request(
        self,
    ):
        request = self.request(
            "Rewrite this notice in Marathi."
        )

        first = document.build_document_prompt(
            request
        )
        second = document.build_document_prompt(
            request
        )

        self.assertEqual(
            first,
            second,
        )
        self.assertIn(
            "Rewrite this notice in Marathi.",
            first,
        )
        self.assertIn(
            "Preserve the requested language",
            first,
        )
        self.assertIn(
            "keep the original meaning",
            first,
        )

    def test_prompt_distinguishes_document_tasks(
        self,
    ):
        prompt = document.build_document_prompt(
            self.request(
                "Summarize my resume notes."
            )
        )

        self.assertIn(
            "drafting, rewriting, summarizing, or resume",
            prompt,
        )
        self.assertIn(
            "For summarizing",
            prompt,
        )
        self.assertIn(
            "For resumes",
            prompt,
        )

    def test_prompt_preserves_facts_and_uses_placeholders(
        self,
    ):
        prompt = document.build_document_prompt(
            self.request(
                "Create a resume for Onkar, B.Sc. CA."
            )
        )

        self.assertIn(
            "Onkar, B.Sc. CA.",
            prompt,
        )
        self.assertIn(
            "Preserve every user-provided name, date, number",
            prompt,
        )
        self.assertIn(
            "[MISSING: graduation year]",
            prompt,
        )
        self.assertIn(
            "Never invent missing facts",
            prompt,
        )

    def test_prompt_forbids_false_file_creation_claims(
        self,
    ):
        prompt = document.build_document_prompt(
            self.request(
                "Give me a PDF resume."
            )
        )

        self.assertIn(
            "Do not claim that a PDF, DOCX",
            prompt,
        )
        self.assertIn(
            "separate artifact tool actually created it",
            prompt,
        )
        self.assertIn(
            "Return text content only",
            prompt,
        )

    def test_direct_handler_rejects_invalid_request(
        self,
    ):
        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            document.build_document_prompt(
                {
                    "message": "unsafe"
                }
            )

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            document.dispatch_document(
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
            "Document prompt is too long",
        ):
            document.build_document_prompt(
                request
            )

    def test_document_module_has_no_artifact_integrations(
        self,
    ):
        source = inspect.getsource(
            document
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
            "httpx",
            "socket",
            "GroqService",
            "RAGService",
            "InternetAgent",
            "DocumentStorage",
            "app.database",
            "app.storage",
            "python-docx",
            "reportlab",
        )

        for token in forbidden_tokens:
            with self.subTest(
                token=token
            ):
                self.assertNotIn(
                    token,
                    source,
                )

    def test_existing_agent_dispatches_remain_stable(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        cases = (
            (
                "coding",
                "Debug this loop.",
                "coding",
            ),
            (
                registry
                .GENERAL_CHAT_AGENT_ID,
                "Hello Onkar",
                "chat",
            ),
            (
                "study",
                "Explain arrays.",
                "study",
            ),
        )

        for agent_id, message, route in cases:
            with self.subTest(
                agent_id=agent_id
            ):
                result = agent_registry.dispatch(
                    agent_id,
                    registry
                    .AgentDispatchRequest(
                        message=message,
                    ),
                )

                self.assertEqual(
                    result.agent_id,
                    agent_id,
                )
                self.assertEqual(
                    result.route,
                    route,
                )
                self.assertIn(
                    message,
                    result.prompt,
                )
                self.assertEqual(
                    result.sources,
                    (),
                )


if __name__ == "__main__":
    unittest.main()
