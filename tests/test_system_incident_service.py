from __future__ import annotations

import unittest
from dataclasses import replace

from app.services.system_health_service import (
    HealthCheckDefinition,
    degraded_outcome,
    disabled_outcome,
    healthy_outcome,
    run_system_health_checks,
    unavailable_outcome,
)
from app.services.system_incident_service import (
    SystemIncidentConfigurationError,
    build_incident_signals,
    incident_reconciliation_payload,
    reconcile_incident_signals,
)


def build_report(
    *definitions: HealthCheckDefinition,
):
    return run_system_health_checks(
        definitions
    )


def definition(
    name,
    outcome,
    *,
    critical,
):
    return HealthCheckDefinition(
        name=name,
        check=lambda: outcome,
        critical=critical,
    )


class SystemIncidentServiceTests(
    unittest.TestCase
):
    def test_healthy_components_create_no_incidents(
        self,
    ):
        report = build_report(
            definition(
                "database",
                healthy_outcome(
                    "postgresql_reachable"
                ),
                critical=True,
            ),
            definition(
                "document_storage",
                healthy_outcome(
                    "r2_reachable"
                ),
                critical=True,
            ),
        )

        self.assertEqual(
            build_incident_signals(
                report
            ),
            (),
        )

    def test_disabled_component_creates_no_incident(
        self,
    ):
        report = build_report(
            definition(
                "document_recovery",
                disabled_outcome(
                    "recovery_disabled"
                ),
                critical=False,
            )
        )

        self.assertEqual(
            build_incident_signals(
                report
            ),
            (),
        )

    def test_degraded_component_creates_warning(
        self,
    ):
        report = build_report(
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            )
        )

        signal = build_incident_signals(
            report
        )[0]

        self.assertEqual(
            signal.severity,
            "warning",
        )
        self.assertEqual(
            signal.source_status,
            "degraded",
        )

    def test_critical_unavailable_component_creates_critical_incident(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        signal = build_incident_signals(
            report
        )[0]

        self.assertEqual(
            signal.severity,
            "critical",
        )
        self.assertTrue(
            signal.critical
        )

    def test_noncritical_unavailable_component_creates_warning(
        self,
    ):
        report = build_report(
            definition(
                "document_recovery",
                unavailable_outcome(
                    "recovery_failed"
                ),
                critical=False,
            )
        )

        signal = build_incident_signals(
            report
        )[0]

        self.assertEqual(
            signal.severity,
            "warning",
        )
        self.assertFalse(
            signal.critical
        )

    def test_incident_order_matches_health_component_order(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            ),
            definition(
                "document_storage",
                degraded_outcome(
                    "storage_latency"
                ),
                critical=True,
            ),
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            ),
        )

        signals = build_incident_signals(
            report
        )

        self.assertEqual(
            [
                signal.component
                for signal in signals
            ],
            [
                "database",
                "document_storage",
                "document_recovery",
            ],
        )

    def test_identical_signal_has_stable_fingerprint(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        first = build_incident_signals(
            report
        )[0]

        second = build_incident_signals(
            report
        )[0]

        self.assertEqual(
            first.fingerprint,
            second.fingerprint,
        )
        self.assertEqual(
            len(first.fingerprint),
            64,
        )

    def test_changed_detail_changes_fingerprint(
        self,
    ):
        first_report = build_report(
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            )
        )

        second_report = build_report(
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_status_unknown"
                ),
                critical=False,
            )
        )

        first = build_incident_signals(
            first_report
        )[0]

        second = build_incident_signals(
            second_report
        )[0]

        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_unsafe_component_detail_is_sanitized(
        self,
    ):
        report = build_report(
            definition(
                "database",
                degraded_outcome(
                    "database_slow"
                ),
                critical=True,
            )
        )

        unsafe_component = replace(
            report.components[0],
            detail=(
                "postgresql://user:"
                "password@host/database"
            ),
        )

        unsafe_report = replace(
            report,
            components=(
                unsafe_component,
            ),
        )

        signal = build_incident_signals(
            unsafe_report
        )[0]

        self.assertEqual(
            signal.detail,
            "check_failed",
        )

        self.assertNotIn(
            "password",
            str(
                signal.to_dict()
            ).casefold(),
        )

    def test_new_signal_is_classified_as_opened(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        result = reconcile_incident_signals(
            (),
            report,
        )

        self.assertEqual(
            len(result.opened),
            1,
        )
        self.assertEqual(
            result.opened[0].component,
            "database",
        )

    def test_identical_signal_is_classified_as_unchanged(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        previous = build_incident_signals(
            report
        )

        result = reconcile_incident_signals(
            previous,
            report,
        )

        self.assertEqual(
            len(result.unchanged),
            1,
        )
        self.assertEqual(
            result.opened,
            (),
        )
        self.assertEqual(
            result.updated,
            (),
        )

    def test_changed_signal_is_classified_as_updated(
        self,
    ):
        previous_report = build_report(
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            )
        )

        current_report = build_report(
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_status_unknown"
                ),
                critical=False,
            )
        )

        previous = build_incident_signals(
            previous_report
        )

        result = reconcile_incident_signals(
            previous,
            current_report,
        )

        self.assertEqual(
            len(result.updated),
            1,
        )
        self.assertEqual(
            result.updated[0].detail,
            "recovery_status_unknown",
        )

    def test_disappearing_signal_is_classified_as_resolved(
        self,
    ):
        previous_report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        current_report = build_report(
            definition(
                "database",
                healthy_outcome(
                    "postgresql_reachable"
                ),
                critical=True,
            )
        )

        previous = build_incident_signals(
            previous_report
        )

        result = reconcile_incident_signals(
            previous,
            current_report,
        )

        self.assertEqual(
            len(result.resolved),
            1,
        )
        self.assertEqual(
            result.active,
            (),
        )

    def test_mixed_reconciliation_is_deterministic(
        self,
    ):
        previous_report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            ),
            definition(
                "document_storage",
                degraded_outcome(
                    "storage_latency"
                ),
                critical=True,
            ),
        )

        current_report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            ),
            definition(
                "document_storage",
                healthy_outcome(
                    "r2_reachable"
                ),
                critical=True,
            ),
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            ),
        )

        previous = build_incident_signals(
            previous_report
        )

        result = reconcile_incident_signals(
            previous,
            current_report,
        )

        self.assertEqual(
            [
                signal.component
                for signal in result.unchanged
            ],
            [
                "database",
            ],
        )

        self.assertEqual(
            [
                signal.component
                for signal in result.resolved
            ],
            [
                "document_storage",
            ],
        )

        self.assertEqual(
            [
                signal.component
                for signal in result.opened
            ],
            [
                "document_recovery",
            ],
        )

    def test_duplicate_previous_keys_are_rejected(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            )
        )

        signal = build_incident_signals(
            report
        )[0]

        with self.assertRaises(
            SystemIncidentConfigurationError
        ):
            reconcile_incident_signals(
                (
                    signal,
                    signal,
                ),
                report,
            )

    def test_invalid_previous_signal_is_rejected(
        self,
    ):
        report = build_report(
            definition(
                "database",
                healthy_outcome(
                    "postgresql_reachable"
                ),
                critical=True,
            )
        )

        with self.assertRaises(
            SystemIncidentConfigurationError
        ):
            reconcile_incident_signals(
                (
                    object(),
                ),
                report,
            )

    def test_payload_contains_transition_counts(
        self,
    ):
        report = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_unreachable"
                ),
                critical=True,
            ),
            definition(
                "document_recovery",
                degraded_outcome(
                    "recovery_failures"
                ),
                critical=False,
            ),
        )

        result = reconcile_incident_signals(
            (),
            report,
        )

        payload = incident_reconciliation_payload(
            result
        )

        self.assertEqual(
            payload["service"],
            "system_incidents",
        )
        self.assertEqual(
            payload["active_count"],
            2,
        )
        self.assertEqual(
            payload["critical_count"],
            1,
        )
        self.assertEqual(
            payload["warning_count"],
            1,
        )
        self.assertEqual(
            payload["opened_count"],
            2,
        )
        self.assertTrue(
            payload["has_critical"]
        )

    def test_invalid_report_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemIncidentConfigurationError
        ):
            build_incident_signals(
                object()
            )


if __name__ == "__main__":
    unittest.main()
