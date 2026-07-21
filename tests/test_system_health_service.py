from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services.system_health_service import (
    MAX_HEALTH_COMPONENTS,
    HealthCheckDefinition,
    HealthCheckOutcome,
    SystemHealthConfigurationError,
    degraded_outcome,
    disabled_outcome,
    healthy_outcome,
    run_system_health_checks,
    system_health_payload,
)


FIXED_TIME = datetime(
    2026,
    7,
    21,
    12,
    30,
    tzinfo=timezone.utc,
)


class IncrementingClock:
    def __init__(
        self,
        *,
        step: float = 0.005,
    ):
        self.value = 100.0
        self.step = step

    def __call__(
        self,
    ) -> float:
        current = self.value
        self.value += self.step
        return current


class SystemHealthServiceTests(
    unittest.TestCase
):
    def run_checks(
        self,
        definitions,
    ):
        return run_system_health_checks(
            definitions,
            now=lambda: FIXED_TIME,
            monotonic=IncrementingClock(),
        )

    def test_all_healthy_components_are_ready(
        self,
    ):
        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="database",
                    check=healthy_outcome,
                ),
                HealthCheckDefinition(
                    name="storage",
                    check=lambda: healthy_outcome(
                        "reachable"
                    ),
                ),
            ]
        )

        self.assertEqual(
            report.status,
            "healthy",
        )
        self.assertTrue(
            report.ready
        )
        self.assertTrue(
            report.healthy
        )
        self.assertFalse(
            report.attention_required
        )
        self.assertEqual(
            report.component_count,
            2,
        )

    def test_critical_unavailable_component_blocks_readiness(
        self,
    ):
        def failing_check():
            raise RuntimeError(
                "secret database connection details"
            )

        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="database",
                    check=failing_check,
                    critical=True,
                )
            ]
        )

        self.assertEqual(
            report.status,
            "unhealthy",
        )
        self.assertFalse(
            report.ready
        )
        self.assertTrue(
            report.attention_required
        )

        component = report.components[0]

        self.assertEqual(
            component.status,
            "unavailable",
        )
        self.assertEqual(
            component.detail,
            "check_failed",
        )

    def test_optional_unavailable_component_is_degraded(
        self,
    ):
        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="database",
                    check=healthy_outcome,
                ),
                HealthCheckDefinition(
                    name="recovery",
                    check=lambda: (
                        HealthCheckOutcome(
                            status="unavailable",
                            detail="not_ready",
                        )
                    ),
                    critical=False,
                ),
            ]
        )

        self.assertEqual(
            report.status,
            "degraded",
        )
        self.assertTrue(
            report.ready
        )
        self.assertFalse(
            report.healthy
        )

    def test_degraded_component_requires_attention(
        self,
    ):
        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="storage",
                    check=lambda: degraded_outcome(
                        "slow_response"
                    ),
                )
            ]
        )

        self.assertEqual(
            report.status,
            "degraded",
        )
        self.assertTrue(
            report.ready
        )
        self.assertTrue(
            report.attention_required
        )

    def test_disabled_component_is_healthy_for_aggregation(
        self,
    ):
        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="optional_ai",
                    check=disabled_outcome,
                    critical=False,
                )
            ]
        )

        self.assertEqual(
            report.status,
            "healthy",
        )
        self.assertTrue(
            report.ready
        )
        self.assertTrue(
            report.healthy
        )
        self.assertEqual(
            report.components[0].status,
            "disabled",
        )

    def test_invalid_probe_result_is_sanitized_as_failure(
        self,
    ):
        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="database",
                    check=lambda: True,
                )
            ]
        )

        component = report.components[0]

        self.assertEqual(
            component.status,
            "unavailable",
        )
        self.assertEqual(
            component.detail,
            "check_failed",
        )

    def test_empty_definition_set_is_initializing(
        self,
    ):
        report = self.run_checks(
            []
        )

        self.assertEqual(
            report.status,
            "initializing",
        )
        self.assertFalse(
            report.ready
        )
        self.assertFalse(
            report.healthy
        )
        self.assertFalse(
            report.attention_required
        )

    def test_duplicate_component_names_are_rejected(
        self,
    ):
        definitions = [
            HealthCheckDefinition(
                name="database",
                check=healthy_outcome,
            ),
            HealthCheckDefinition(
                name="database",
                check=healthy_outcome,
            ),
        ]

        with self.assertRaises(
            SystemHealthConfigurationError
        ):
            self.run_checks(
                definitions
            )

    def test_invalid_component_name_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemHealthConfigurationError
        ):
            HealthCheckDefinition(
                name="Database URL",
                check=healthy_outcome,
            )

    def test_invalid_detail_code_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemHealthConfigurationError
        ):
            HealthCheckOutcome(
                status="unavailable",
                detail="password=secret",
            )

    def test_component_limit_is_enforced(
        self,
    ):
        definitions = [
            HealthCheckDefinition(
                name=f"component_{index}",
                check=healthy_outcome,
            )
            for index in range(
                MAX_HEALTH_COMPONENTS + 1
            )
        ]

        with self.assertRaises(
            SystemHealthConfigurationError
        ):
            self.run_checks(
                definitions
            )

    def test_payload_contains_only_sanitized_fields(
        self,
    ):
        def failing_check():
            raise RuntimeError(
                "postgresql://username:password@host/database"
            )

        report = self.run_checks(
            [
                HealthCheckDefinition(
                    name="database",
                    check=failing_check,
                )
            ]
        )

        payload = system_health_payload(
            report
        )

        serialized = repr(
            payload
        ).casefold()

        self.assertEqual(
            payload["service"],
            "system_health",
        )
        self.assertEqual(
            payload["components"][0]["detail"],
            "check_failed",
        )
        self.assertNotIn(
            "password",
            serialized,
        )
        self.assertNotIn(
            "postgresql://",
            serialized,
        )
        self.assertNotIn(
            "username",
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
