from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError

from app.agents import registry
from app.agents import selection


class AgentSelectionFoundationTests(
    unittest.TestCase
):
    def test_default_selection_resolves_general_chat(
        self,
    ):
        result = (
            selection
            .resolve_agent_selection()
        )

        self.assertEqual(
            result.agent_id,
            registry
            .GENERAL_CHAT_AGENT_ID,
        )
        self.assertEqual(
            result.name,
            "General Chat",
        )
        self.assertEqual(
            result.capabilities,
            (
                registry
                .GENERAL_CHAT_CAPABILITY,
            ),
        )
        self.assertTrue(
            result.used_default
        )

    def test_explicit_selection_resolves_all_agents(
        self,
    ):
        cases = (
            (
                "coding",
                "Coding Agent",
            ),
            (
                "document",
                "Document Agent",
            ),
            (
                "general-chat",
                "General Chat",
            ),
            (
                "market-research",
                "Market Research Agent",
            ),
            (
                "study",
                "Study Agent",
            ),
        )

        for agent_id, name in cases:
            with self.subTest(
                agent_id=agent_id
            ):
                result = (
                    selection
                    .resolve_agent_selection(
                        agent_id
                    )
                )

                self.assertEqual(
                    result.agent_id,
                    agent_id,
                )
                self.assertEqual(
                    result.name,
                    name,
                )
                self.assertFalse(
                    result.used_default
                )

    def test_surrounding_whitespace_is_normalized(
        self,
    ):
        result = (
            selection
            .resolve_agent_selection(
                "  study  "
            )
        )

        self.assertEqual(
            result.agent_id,
            "study",
        )
        self.assertFalse(
            result.used_default
        )

    def test_result_is_immutable_and_safe(
        self,
    ):
        result = (
            selection
            .resolve_agent_selection(
                "document"
            )
        )

        self.assertIsInstance(
            result.capabilities,
            tuple,
        )
        self.assertNotIn(
            "handler",
            result.__slots__,
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            result.name = "changed"

    def test_invalid_supplied_ids_are_generic(
        self,
    ):
        cases = (
            "",
            "   ",
            5,
            True,
            object(),
            (
                "x"
                * (
                    registry
                    .MAX_AGENT_ID_LENGTH
                    + 1
                )
            ),
            "Study",
        )

        for value in cases:
            with self.subTest(
                value=repr(value)
            ):
                with self.assertRaisesRegex(
                    selection
                    .AgentSelectionError,
                    "^Unable to select agent[.]$",
                ):
                    (
                        selection
                        .resolve_agent_selection(
                            value
                        )
                    )

    def test_unknown_agent_is_generic(
        self,
    ):
        with self.assertRaisesRegex(
            selection
            .AgentSelectionError,
            "^Unable to select agent[.]$",
        ):
            (
                selection
                .resolve_agent_selection(
                    "missing-agent"
                )
            )

    def test_invalid_registry_is_rejected(
        self,
    ):
        with self.assertRaisesRegex(
            selection
            .AgentSelectionError,
            "^Unable to select agent[.]$",
        ):
            (
                selection
                .resolve_agent_selection(
                    "study",
                    registry={
                        "study": "unsafe"
                    },
                )
            )

    def test_resolution_does_not_run_handler(
        self,
    ):
        calls = []

        def handler(request):
            calls.append(request)
            raise AssertionError(
                "handler must not run"
            )

        agent_registry = (
            registry.AgentRegistry(
                (
                    registry.AgentDefinition(
                        agent_id="safe-agent",
                        name="Safe Agent",
                        description=(
                            "Selection-only test agent."
                        ),
                        capabilities=(
                            "safe.select",
                        ),
                        handler=handler,
                    ),
                )
            )
        )

        result = (
            selection
            .resolve_agent_selection(
                "safe-agent",
                registry=agent_registry,
            )
        )

        self.assertEqual(
            result.agent_id,
            "safe-agent",
        )
        self.assertEqual(
            calls,
            [],
        )

    def test_module_has_no_external_integrations(
        self,
    ):
        source = inspect.getsource(
            selection
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
                "dataclasses",
                "app.agents.registry",
            },
        )

        forbidden_fragments = (
            ".dispatch(",
            "generate_reply",
            "InternetAgent(",
            "TavilyClient(",
            "GroqService(",
            "RAGService(",
            "requests.",
            "httpx.",
            "socket.",
            "subprocess.",
            "os.system(",
            "Popen(",
            "open(",
            "app.database",
            "app.storage",
        )

        for fragment in forbidden_fragments:
            with self.subTest(
                fragment=fragment
            ):
                self.assertNotIn(
                    fragment,
                    source,
                )

    def test_existing_registry_dispatches_remain_stable(
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
                "document",
                "Rewrite this notice.",
                "document",
            ),
            (
                registry
                .GENERAL_CHAT_AGENT_ID,
                "Hello Onkar",
                "chat",
            ),
            (
                "market-research",
                "Compare two products.",
                "market-research",
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
