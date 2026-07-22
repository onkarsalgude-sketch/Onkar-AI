from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import insert

from app.config.database import DatabaseSettings
from app.database.engine import build_database_engine
from app.database.migrations import initialize_schema
from app.database.schema import system_incidents
from app.services.system_health_service import (
    HealthCheckDefinition,
    degraded_outcome,
    healthy_outcome,
    run_system_health_checks,
    unavailable_outcome,
)
from app.services.system_incident_history_service import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_RETENTION_LIMIT,
    MAX_HISTORY_LIMIT,
    SystemIncidentHistoryError,
    list_system_incidents,
    load_open_incident_signals,
    record_system_incident_evaluation,
    summarize_system_incidents,
)


def build_sqlite_engine(
    database_path: Path,
):
    return build_database_engine(
        DatabaseSettings(
            backend="sqlite",
            database_url=None,
            sqlite_path=database_path,
            require_persistence=False,
            pool_size=5,
            connect_timeout_seconds=10,
        )
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


def build_report(
    *definitions: HealthCheckDefinition,
):
    return run_system_health_checks(
        definitions
    )


def healthy_database_report():
    return build_report(
        definition(
            "database",
            healthy_outcome(
                "postgresql_reachable"
            ),
            critical=True,
        )
    )


def unavailable_database_report():
    return build_report(
        definition(
            "database",
            unavailable_outcome(
                "database_unreachable"
            ),
            critical=True,
        )
    )


class SequentialIds:
    def __init__(
        self,
        *values: str,
    ):
        self._values = iter(
            values
        )

    def __call__(self):
        return next(
            self._values
        )


class TrackingCursor:
    rowcount = 0

    def execute(
        self,
        sql,
        parameters=None,
    ):
        raise RuntimeError(
            "temporary persistence failure"
        )


class TrackingConnection:
    def __init__(self):
        self.rollback_called = False
        self.close_called = False

    def execute(
        self,
        sql,
        parameters=None,
    ):
        return None

    def cursor(self):
        return TrackingCursor()

    def commit(self):
        raise AssertionError(
            "commit must not be called"
        )

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


class SystemIncidentHistoryServiceTests(
    unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.database_path = (
            Path(
                self.temporary_directory.name
            )
            / "incident-history.db"
        )

        self.engine = build_sqlite_engine(
            self.database_path
        )

        initialize_schema(
            self.engine
        )

        self.connection_factory = (
            lambda path: sqlite3.connect(
                path
            )
        )

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def record(
        self,
        report,
        observed_at,
        *,
        ids=(),
        retention_limit=(
            DEFAULT_RETENTION_LIMIT
        ),
    ):
        return record_system_incident_evaluation(
            report,
            observed_at=observed_at,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
            incident_id_factory=(
                SequentialIds(
                    *ids
                )
                if ids
                else SequentialIds(
                    "incident-default"
                )
            ),
            retention_limit=retention_limit,
        )

    def list(
        self,
        limit=DEFAULT_HISTORY_LIMIT,
        *,
        state=None,
    ):
        return list_system_incidents(
            limit,
            state=state,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

    def test_constants_match_bounded_contract(
        self,
    ):
        self.assertEqual(
            DEFAULT_HISTORY_LIMIT,
            20,
        )
        self.assertEqual(
            MAX_HISTORY_LIMIT,
            100,
        )
        self.assertEqual(
            DEFAULT_RETENTION_LIMIT,
            100,
        )

    def test_healthy_evaluation_creates_no_history(
        self,
    ):
        payload = self.record(
            healthy_database_report(),
            "2026-07-21T10:00:00Z",
        )

        self.assertEqual(
            payload["active_count"],
            0,
        )
        self.assertEqual(
            self.list(),
            [],
        )

    def test_opened_incident_is_persisted_safely(
        self,
    ):
        payload = self.record(
            unavailable_database_report(),
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-open-1",
            ),
        )

        rows = self.list()

        self.assertEqual(
            payload["opened_count"],
            1,
        )
        self.assertEqual(
            len(rows),
            1,
        )

        row = rows[0]

        self.assertEqual(
            row["incident_id"],
            "incident-open-1",
        )
        self.assertEqual(
            row["state"],
            "open",
        )
        self.assertEqual(
            row["severity"],
            "critical",
        )
        self.assertEqual(
            row["occurrence_count"],
            1,
        )
        self.assertIsNone(
            row["resolved_at"]
        )

        serialized = str(
            row
        ).casefold()

        for forbidden in (
            "password",
            "database_url",
            "traceback",
            "document_id",
            "filename",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_unchanged_observation_increments_occurrence(
        self,
    ):
        report = unavailable_database_report()

        self.record(
            report,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-repeat-1",
            ),
        )

        payload = self.record(
            report,
            "2026-07-21T10:01:00Z",
        )

        row = self.list()[0]

        self.assertEqual(
            payload["unchanged_count"],
            1,
        )
        self.assertEqual(
            row["incident_id"],
            "incident-repeat-1",
        )
        self.assertEqual(
            row["occurrence_count"],
            2,
        )
        self.assertEqual(
            row["last_seen_at"],
            "2026-07-21T10:01:00+00:00",
        )

    def test_updated_observation_replaces_sanitized_state(
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
                unavailable_outcome(
                    "recovery_failed"
                ),
                critical=False,
            )
        )

        self.record(
            first_report,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-update-1",
            ),
        )

        original = self.list()[0]

        payload = self.record(
            second_report,
            "2026-07-21T10:02:00Z",
        )

        updated = self.list()[0]

        self.assertEqual(
            payload["updated_count"],
            1,
        )
        self.assertEqual(
            updated["incident_id"],
            "incident-update-1",
        )
        self.assertEqual(
            updated["source_status"],
            "unavailable",
        )
        self.assertEqual(
            updated["detail"],
            "recovery_failed",
        )
        self.assertEqual(
            updated["occurrence_count"],
            2,
        )
        self.assertNotEqual(
            updated["fingerprint"],
            original["fingerprint"],
        )

    def test_resolution_preserves_last_active_state(
        self,
    ):
        self.record(
            unavailable_database_report(),
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-resolve-1",
            ),
        )

        payload = self.record(
            healthy_database_report(),
            "2026-07-21T10:05:00Z",
        )

        row = self.list()[0]

        self.assertEqual(
            payload["resolved_count"],
            1,
        )
        self.assertEqual(
            row["state"],
            "resolved",
        )
        self.assertEqual(
            row["last_seen_at"],
            "2026-07-21T10:00:00+00:00",
        )
        self.assertEqual(
            row["resolved_at"],
            "2026-07-21T10:05:00+00:00",
        )
        self.assertEqual(
            row["detail"],
            "database_unreachable",
        )

    def test_reopening_creates_new_lifecycle_row(
        self,
    ):
        unhealthy = unavailable_database_report()
        healthy = healthy_database_report()

        self.record(
            unhealthy,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-cycle-1",
            ),
        )

        self.record(
            healthy,
            "2026-07-21T10:01:00Z",
        )

        self.record(
            unhealthy,
            "2026-07-21T10:02:00Z",
            ids=(
                "incident-cycle-2",
            ),
        )

        rows = self.list()

        self.assertEqual(
            len(rows),
            2,
        )
        self.assertEqual(
            {
                row["incident_id"]
                for row in rows
            },
            {
                "incident-cycle-1",
                "incident-cycle-2",
            },
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in rows
                    if row["state"] == "open"
                ]
            ),
            1,
        )

    def test_mixed_transitions_are_atomic(
        self,
    ):
        first = build_report(
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

        second = build_report(
            definition(
                "database",
                unavailable_outcome(
                    "database_timeout"
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

        self.record(
            first,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-db",
                "incident-storage",
            ),
        )

        payload = self.record(
            second,
            "2026-07-21T10:01:00Z",
            ids=(
                "incident-recovery",
            ),
        )

        self.assertEqual(
            payload["opened_count"],
            1,
        )
        self.assertEqual(
            payload["updated_count"],
            1,
        )
        self.assertEqual(
            payload["resolved_count"],
            1,
        )

        rows = self.list()

        state_by_component = {
            row["component"]: row["state"]
            for row in rows
        }

        self.assertEqual(
            state_by_component,
            {
                "database": "open",
                "document_storage": "resolved",
                "document_recovery": "open",
            },
        )

    def test_retention_prunes_only_oldest_resolved_rows(
        self,
    ):
        unhealthy = unavailable_database_report()
        healthy = healthy_database_report()

        for index in range(3):
            hour = index * 2

            self.record(
                unhealthy,
                (
                    "2026-07-21T"
                    + str(10 + hour).zfill(2)
                    + ":00:00Z"
                ),
                ids=(
                    "incident-retained-"
                    + str(index),
                ),
                retention_limit=2,
            )

            self.record(
                healthy,
                (
                    "2026-07-21T"
                    + str(11 + hour).zfill(2)
                    + ":00:00Z"
                ),
                retention_limit=2,
            )

        self.record(
            unhealthy,
            "2026-07-21T16:00:00Z",
            ids=(
                "incident-open-current",
            ),
            retention_limit=2,
        )

        rows = self.list()

        resolved = [
            row
            for row in rows
            if row["state"] == "resolved"
        ]

        open_rows = [
            row
            for row in rows
            if row["state"] == "open"
        ]

        self.assertEqual(
            len(resolved),
            2,
        )
        self.assertEqual(
            len(open_rows),
            1,
        )
        self.assertEqual(
            open_rows[0]["incident_id"],
            "incident-open-current",
        )

    def test_list_filters_state_and_orders_newest_first(
        self,
    ):
        unhealthy = unavailable_database_report()

        self.record(
            unhealthy,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-old",
            ),
        )

        self.record(
            healthy_database_report(),
            "2026-07-21T10:01:00Z",
        )

        self.record(
            unhealthy,
            "2026-07-21T10:02:00Z",
            ids=(
                "incident-new",
            ),
        )

        open_rows = self.list(
            state="open"
        )

        resolved_rows = self.list(
            state="resolved"
        )

        self.assertEqual(
            [
                row["incident_id"]
                for row in open_rows
            ],
            [
                "incident-new",
            ],
        )

        self.assertEqual(
            [
                row["incident_id"]
                for row in resolved_rows
            ],
            [
                "incident-old",
            ],
        )

    def test_summary_returns_operational_counts(
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

        self.record(
            report,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-summary-db",
                "incident-summary-recovery",
            ),
        )

        summary = summarize_system_incidents(
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

        self.assertEqual(
            summary["total_incidents"],
            2,
        )
        self.assertEqual(
            summary["active_count"],
            2,
        )
        self.assertEqual(
            summary["active_warning_count"],
            1,
        )
        self.assertEqual(
            summary["active_critical_count"],
            1,
        )
        self.assertTrue(
            summary["has_active_critical"]
        )
        self.assertEqual(
            summary["total_occurrences"],
            2,
        )

    def test_unsafe_detail_is_sanitized_before_persistence(
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

        self.record(
            unsafe_report,
            "2026-07-21T10:00:00Z",
            ids=(
                "incident-sanitized",
            ),
        )

        row = self.list()[0]

        self.assertEqual(
            row["detail"],
            "check_failed",
        )
        self.assertNotIn(
            "password",
            str(
                row
            ).casefold(),
        )

    def test_limits_states_and_timestamps_are_validated(
        self,
    ):
        for invalid_limit in (
            0,
            MAX_HISTORY_LIMIT + 1,
            True,
            "invalid",
        ):
            with self.subTest(
                invalid_limit=invalid_limit
            ):
                with self.assertRaises(
                    SystemIncidentHistoryError
                ):
                    self.list(
                        invalid_limit
                    )

        with self.assertRaises(
            SystemIncidentHistoryError
        ):
            self.list(
                state="unknown"
            )

        with self.assertRaises(
            SystemIncidentHistoryError
        ):
            self.record(
                unavailable_database_report(),
                "not-a-timestamp",
                ids=(
                    "incident-invalid-time",
                ),
            )

    def test_backward_timestamp_rolls_back(
        self,
    ):
        report = unavailable_database_report()

        self.record(
            report,
            "2026-07-21T10:05:00Z",
            ids=(
                "incident-clock",
            ),
        )

        with self.assertRaises(
            SystemIncidentHistoryError
        ):
            self.record(
                report,
                "2026-07-21T10:04:00Z",
            )

        row = self.list()[0]

        self.assertEqual(
            row["occurrence_count"],
            1,
        )
        self.assertEqual(
            row["last_seen_at"],
            "2026-07-21T10:05:00+00:00",
        )

    def test_duplicate_open_keys_are_rejected(
        self,
    ):
        from app.services.system_incident_service import (
            build_incident_signals,
        )

        signal = build_incident_signals(
            unavailable_database_report()
        )[0]

        values = {
            "incident_key": (
                "system_health:database"
            ),
            "component": "database",
            "severity": "critical",
            "source_status": "unavailable",
            "detail": "database_unreachable",
            "critical": 1,
            "state": "open",
            "fingerprint": signal.fingerprint,
            "opened_at": (
                "2026-07-21T10:00:00+00:00"
            ),
            "last_seen_at": (
                "2026-07-21T10:00:00+00:00"
            ),
            "resolved_at": None,
            "occurrence_count": 1,
        }

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    system_incidents
                ),
                [
                    {
                        **values,
                        "incident_id": (
                            "incident-duplicate-1"
                        ),
                    },
                    {
                        **values,
                        "incident_id": (
                            "incident-duplicate-2"
                        ),
                    },
                ],
            )

        with self.assertRaises(
            SystemIncidentHistoryError
        ):
            load_open_incident_signals(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
            )

    def test_corrupt_fingerprint_is_rejected(
        self,
    ):
        values = {
            "incident_id": "incident-corrupt",
            "incident_key": (
                "system_health:database"
            ),
            "component": "database",
            "severity": "critical",
            "source_status": "unavailable",
            "detail": "database_unreachable",
            "critical": 1,
            "state": "open",
            "fingerprint": "0" * 64,
            "opened_at": (
                "2026-07-21T10:00:00+00:00"
            ),
            "last_seen_at": (
                "2026-07-21T10:00:00+00:00"
            ),
            "resolved_at": None,
            "occurrence_count": 1,
        }

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    system_incidents
                ).values(
                    **values
                )
            )

        with self.assertRaises(
            SystemIncidentHistoryError
        ):
            load_open_incident_signals(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
            )

    def test_write_failure_is_generic_and_rolls_back(
        self,
    ):
        connection = TrackingConnection()

        with self.assertRaises(
            SystemIncidentHistoryError
        ) as caught:
            record_system_incident_evaluation(
                unavailable_database_report(),
                observed_at=(
                    "2026-07-21T10:00:00Z"
                ),
                connection_factory=(
                    lambda _path: connection
                ),
                incident_id_factory=(
                    lambda: "incident-failure"
                ),
            )

        self.assertEqual(
            str(
                caught.exception
            ),
            "System incident history write failed.",
        )
        self.assertTrue(
            connection.rollback_called
        )
        self.assertTrue(
            connection.close_called
        )

    def test_read_failure_is_generic(
        self,
    ):
        def failing_factory(
            _path,
        ):
            raise RuntimeError(
                "database credential leaked"
            )

        with self.assertRaises(
            SystemIncidentHistoryError
        ) as caught:
            list_system_incidents(
                connection_factory=(
                    failing_factory
                )
            )

        self.assertEqual(
            str(
                caught.exception
            ),
            "System incident history read failed.",
        )
        self.assertNotIn(
            "credential",
            str(
                caught.exception
            ).casefold(),
        )

    def test_datetime_is_normalized_to_utc(
        self,
    ):
        self.record(
            unavailable_database_report(),
            datetime(
                2026,
                7,
                21,
                15,
                30,
                tzinfo=timezone.utc,
            ),
            ids=(
                "incident-datetime",
            ),
        )

        row = self.list()[0]

        self.assertEqual(
            row["opened_at"],
            "2026-07-21T15:30:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
