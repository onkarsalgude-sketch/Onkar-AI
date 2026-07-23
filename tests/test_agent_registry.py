from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

from app.agents import registry


class AgentRegistryTests(
    unittest.TestCase
):
    def definition(
        self,
        *,
        agent_id="study-agent",
        capabilities=(
            "study.explain",
            "study.quiz",
        ),
        handler=None,
    ):
        resolved_handler = (
            handler
            or Mock(
                return_value=(
                    registry.AgentDispatchResult(
                        agent_id=agent_id,
                        route="agent",
                        prompt="handled",
                    )
                )
            )
        )

        return registry.AgentDefinition(
            agent_id=agent_id,
            name="Study Agent",
            description=(
                "Provides safe study assistance."
            ),
            capabilities=capabilities,
            handler=resolved_handler,
        )

    def test_default_registry_has_general_chat_and_study(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )

        records = (
            agent_registry.list_agents()
        )

        self.assertEqual(
            tuple(
                record["agent_id"]
                for record in records
            ),
            (
                registry
                .GENERAL_CHAT_AGENT_ID,
                "study",
            ),
        )
        self.assertEqual(
            records[0]["capabilities"],
            (
                registry
                .GENERAL_CHAT_CAPABILITY,
            ),
        )
        self.assertEqual(
            records[1]["capabilities"],
            (
                "study.explain",
                "study.quiz",
                "study.revise",
            ),
        )

        for record in records:
            self.assertNotIn(
                "handler",
                record,
            )

            with self.assertRaises(
                TypeError
            ):
                record["name"] = "changed"

    def test_definition_is_immutable_and_deterministic(
        self,
    ):
        definition = self.definition(
            capabilities=(
                "study.quiz",
                "study.explain",
            )
        )

        self.assertEqual(
            definition.capabilities,
            (
                "study.explain",
                "study.quiz",
            ),
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            definition.name = "changed"

    def test_lookup_is_safe_and_missing_is_explicit(
        self,
    ):
        definition = self.definition()
        agent_registry = (
            registry.AgentRegistry(
                (definition,)
            )
        )

        self.assertIs(
            agent_registry.get(
                "study-agent"
            ),
            definition,
        )
        self.assertIsNone(
            agent_registry.get(
                "missing-agent"
            )
        )

        with self.assertRaises(
            registry.AgentNotFoundError
        ):
            agent_registry.require(
                "missing-agent"
            )

    def test_duplicate_agent_id_is_rejected(
        self,
    ):
        agent_registry = (
            registry.AgentRegistry(
                (
                    self.definition(),
                )
            )
        )

        with self.assertRaises(
            registry
            .AgentAlreadyRegisteredError
        ):
            agent_registry.register(
                self.definition()
            )

    def test_invalid_definition_inputs_are_rejected(
        self,
    ):
        invalid_values = (
            {
                "agent_id": (
                    " Study-Agent "
                ),
            },
            {
                "agent_id": (
                    "Study-Agent"
                ),
            },
            {
                "capabilities": (),
            },
            {
                "capabilities": (
                    "study.quiz",
                    "study.quiz",
                ),
            },
            {
                "handler": (
                    "app.agents.study:run"
                ),
            },
        )

        for changes in invalid_values:
            with self.subTest(
                changes=changes
            ):
                values = {
                    "agent_id": (
                        "study-agent"
                    ),
                    "capabilities": (
                        "study.explain",
                    ),
                    "handler": Mock(),
                }
                values.update(changes)

                with self.assertRaises(
                    registry
                    .AgentRegistryValidationError
                ):
                    self.definition(
                        **values
                    )

    def test_registry_listing_is_sorted(
        self,
    ):
        agent_registry = (
            registry.AgentRegistry(
                (
                    self.definition(
                        agent_id="z-agent",
                        capabilities=(
                            "z.run",
                        ),
                    ),
                    self.definition(
                        agent_id="a-agent",
                        capabilities=(
                            "a.run",
                        ),
                    ),
                )
            )
        )

        self.assertEqual(
            tuple(
                record["agent_id"]
                for record
                in agent_registry
                .list_agents()
            ),
            (
                "a-agent",
                "z-agent",
            ),
        )

    def test_general_chat_dispatch_is_stable(
        self,
    ):
        agent_registry = (
            registry
            .build_default_agent_registry()
        )
        request = (
            registry.AgentDispatchRequest(
                message=(
                    "  Hello    Onkar  "
                ),
                chat_id=7,
                model_id="model-1",
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

    def test_invalid_request_stops_before_handler(
        self,
    ):
        handler = Mock()
        agent_registry = (
            registry.AgentRegistry(
                (
                    self.definition(
                        handler=handler
                    ),
                )
            )
        )

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            agent_registry.dispatch(
                "study-agent",
                {
                    "message": "unsafe"
                },
            )

        handler.assert_not_called()

        with self.assertRaises(
            registry
            .AgentRegistryValidationError
        ):
            registry.AgentDispatchRequest(
                message="",
            )

    def test_handler_failure_is_generic(
        self,
    ):
        secret = (
            "provider://private-token"
        )
        handler = Mock(
            side_effect=RuntimeError(
                secret
            )
        )
        agent_registry = (
            registry.AgentRegistry(
                (
                    self.definition(
                        handler=handler
                    ),
                )
            )
        )

        with self.assertRaises(
            registry.AgentDispatchError
        ) as captured:
            agent_registry.dispatch(
                "study-agent",
                registry
                .AgentDispatchRequest(
                    message="Explain this",
                ),
            )

        self.assertEqual(
            str(captured.exception),
            "Agent dispatch failed.",
        )
        self.assertNotIn(
            secret,
            str(captured.exception),
        )

    def test_invalid_handler_result_is_rejected(
        self,
    ):
        invalid_results = (
            None,
            registry.AgentDispatchResult(
                agent_id="other-agent",
                route="agent",
                prompt="wrong",
            ),
        )

        for result in invalid_results:
            with self.subTest(
                result=result
            ):
                agent_registry = (
                    registry.AgentRegistry(
                        (
                            self.definition(
                                handler=Mock(
                                    return_value=(
                                        result
                                    )
                                )
                            ),
                        )
                    )
                )

                with self.assertRaises(
                    registry
                    .AgentDispatchError
                ):
                    agent_registry.dispatch(
                        "study-agent",
                        registry
                        .AgentDispatchRequest(
                            message=(
                                "Explain this"
                            ),
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
