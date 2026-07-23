from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError

from app.agents import market_research
from app.agents import registry


class MarketResearchAgentFoundationTests(
    unittest.TestCase
):
    def request(
        self,
        message=(
            "Compare budget smartphones in India "
            "for a student."
        ),
    ):
        return registry.AgentDispatchRequest(
            message=message,
            chat_id=41,
            model_id="model-1",
        )

    def test_definition_contract_is_explicit_and_immutable(
        self,
    ):
        definition = (
            market_research
            .build_market_research_agent_definition()
        )

        self.assertEqual(
            definition.agent_id,
            "market-research",
        )
        self.assertEqual(
            definition.name,
            "Market Research Agent",
        )
        self.assertEqual(
            definition.capabilities,
            (
                "market-research.compare",
                "market-research.plan",
                "market-research.summarize",
                "market-research.verify",
            ),
        )
        self.assertIs(
            definition.handler,
            market_research
            .dispatch_market_research,
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            definition.name = "changed"

    def test_default_registry_dispatches_market_research_agent(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        result = agent_registry.dispatch(
            "market-research",
            self.request(),
        )

        self.assertEqual(
            result.agent_id,
            "market-research",
        )
        self.assertEqual(
            result.route,
            "market-research",
        )
        self.assertEqual(
            result.sources,
            (),
        )

    def test_prompt_is_deterministic_and_preserves_request(
        self,
    ):
        request = self.request(
            "Compare laptops under INR 50000 in Pune."
        )

        first = (
            market_research
            .build_market_research_prompt(
                request
            )
        )
        second = (
            market_research
            .build_market_research_prompt(
                request
            )
        )

        self.assertEqual(
            first,
            second,
        )
        self.assertIn(
            "Compare laptops under INR 50000 in Pune.",
            first,
        )
        self.assertIn(
            "Preserve every user-provided market",
            first,
        )
        self.assertIn(
            "requested output format exactly",
            first,
        )

    def test_prompt_distinguishes_research_tasks(
        self,
    ):
        prompt = (
            market_research
            .build_market_research_prompt(
                self.request(
                    "Verify this market-size claim."
                )
            )
        )

        self.assertIn(
            "comparison, planning, summarization, or verification",
            prompt,
        )
        self.assertIn(
            "Compare sources when they disagree",
            prompt,
        )

    def test_prompt_requires_fresh_attributable_verification(
        self,
    ):
        prompt = (
            market_research
            .build_market_research_prompt(
                self.request(
                    "What is the current price?"
                )
            )
        )

        self.assertIn(
            "require fresh verification",
            prompt,
        )
        self.assertIn(
            "dated and attributable sources",
            prompt,
        )
        self.assertIn(
            "before presenting it as current",
            prompt,
        )

    def test_prompt_separates_facts_estimates_and_inferences(
        self,
    ):
        prompt = (
            market_research
            .build_market_research_prompt(
                self.request(
                    "Estimate demand next year."
                )
            )
        )

        self.assertIn(
            "verified facts, estimates, assumptions, and inferences",
            prompt,
        )
        self.assertIn(
            "explain the uncertainty",
            prompt,
        )

    def test_prompt_forbids_invented_market_evidence(
        self,
    ):
        prompt = (
            market_research
            .build_market_research_prompt(
                self.request(
                    "Summarize a new product market."
                )
            )
        )

        self.assertIn(
            "Never invent prices, market sizes",
            prompt,
        )
        self.assertIn(
            "citations, source titles, publication dates",
            prompt,
        )
        self.assertIn(
            "say what must be verified instead of guessing",
            prompt,
        )

    def test_prompt_blocks_financial_signals_and_false_research_claims(
        self,
    ):
        prompt = (
            market_research
            .build_market_research_prompt(
                self.request(
                    "Tell me which stock to buy today."
                )
            )
        )

        self.assertIn(
            "Do not provide personalized financial advice",
            prompt,
        )
        self.assertIn(
            "trade signals",
            prompt,
        )
        self.assertIn(
            "unsupported buy or sell recommendations",
            prompt,
        )
        self.assertIn(
            "Do not claim that web research",
            prompt,
        )

    def test_direct_handler_rejects_invalid_request(
        self,
    ):
        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            market_research.build_market_research_prompt(
                {
                    "message": "invalid"
                }
            )

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            market_research.dispatch_market_research(
                {
                    "message": "invalid"
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
            "Market Research prompt is too long",
        ):
            (
                market_research
                .build_market_research_prompt(
                    request
                )
            )

    def test_module_has_no_network_or_data_integrations(
        self,
    ):
        source = inspect.getsource(
            market_research
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

        forbidden_fragments = (
            "subprocess.",
            "os.system(",
            "Popen(",
            "shell=True",
            "importlib.",
            "__import__(",
            "eval(",
            "exec(",
            "open(",
            "requests.",
            "httpx.",
            "socket.",
            "TavilyClient(",
            "InternetAgent(",
            "GroqService(",
            "RAGService(",
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
