from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config.database import DatabaseSettings
from app.config.system_incident_alerting import (
    SystemIncidentAlertingSettings,
)
from app.database.engine import (
    build_database_engine,
)
from app.database.migrations import (
    initialize_schema,
)
from app.services.system_incident_alert_outbox_service import (
    MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES,
    SystemIncidentAlertOutboxError,
    enqueue_system_incident_alert,
)


FIXED_NOW = datetime(
    2026,
    7,
    22,
    10,
    30,
    0,
    tzinfo=timezone.utc,
)


def transition_signal() -> dict:
    return {
        "incident_key": (
            "system_health:database"
        ),
        "component": "database",
        "severity": "critical",
        "source_status": "unavailable",
        "detail": "database_unreachable",
        "critical": True,
        "fingerprint": "a" * 64,
    }


def opened_evaluation() -> dict:
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T10:29:00+00:00"
        ),
        "opened": [
            transition_signal()
        ],
        "updated": [],
        "resolved": [],
        "unchanged": [],
    }


def unchanged_evaluation() -> dict:
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T10:29:00+00:00"
        ),
        "opened": [],
        "updated": [],
        "resolved": [],
        "unchanged": [
            transition_signal()
        ],
    }


class SystemIncidentAlertOutboxServiceTests(
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
            / "alert-outbox.db"
        )

        self.engine = build_database_engine(
            DatabaseSettings(
                backend="sqlite",
                database_url=None,
                sqlite_path=self.database_path,
                require_persistence=False,
                pool_size=5,
                connect_timeout_seconds=10,
            )
        )

        initialize_schema(
            self.engine
        )

        self.engine.dispose()

        self.enabled_settings = (
            SystemIncidentAlertingSettings(
                enabled=True,
                webhook_url=(
                    "https://alerts.example.test/hook"
                ),
                timeout_seconds=2,
            )
        )

        self.disabled_settings = (
            SystemIncidentAlertingSettings(
                enabled=False,
                webhook_url="",
                timeout_seconds=2,
            )
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def read_rows(self):
        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        try:
            return connection.execute(
                """
                SELECT
                    delivery_id,
                    payload_json,
                    state,
                    attempt_count,
                    max_attempts,
                    next_attempt_at,
                    claimed_at,
                    claim_token,
                    created_at,
                    updated_at,
                    completed_at
                FROM system_incident_alert_outbox
                ORDER BY delivery_id
                """
            ).fetchall()
        finally:
            connection.close()

    def test_disabled_alerts_create_no_row(self):
        connection_factory = MagicMock(
            side_effect=AssertionError(
                "connection must not be opened"
            )
        )

        with patch(
            (
                "app.services."
                "system_incident_alert_outbox_service."
                "build_system_incident_alert_payload"
            )
        ) as builder:
            result = enqueue_system_incident_alert(
                self.disabled_settings,
                opened_evaluation(),
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    connection_factory
                ),
            )

        self.assertFalse(
            result["queued"]
        )
        self.assertEqual(
            result["reason"],
            "disabled",
        )
        builder.assert_not_called()
        connection_factory.assert_not_called()
        self.assertEqual(
            self.read_rows(),
            [],
        )

    def test_unchanged_only_evaluation_creates_no_row(
        self,
    ):
        connection_factory = MagicMock(
            side_effect=AssertionError(
                "connection must not be opened"
            )
        )

        result = enqueue_system_incident_alert(
            self.enabled_settings,
            unchanged_evaluation(),
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                connection_factory
            ),
            now=lambda: FIXED_NOW,
        )

        self.assertFalse(
            result["queued"]
        )
        self.assertEqual(
            result["reason"],
            "no_transitions",
        )
        connection_factory.assert_not_called()
        self.assertEqual(
            self.read_rows(),
            [],
        )

    def test_opened_transition_is_queued_safely(
        self,
    ):
        result = enqueue_system_incident_alert(
            self.enabled_settings,
            opened_evaluation(),
            db_path=str(
                self.database_path
            ),
            delivery_id_factory=(
                lambda: "delivery-1"
            ),
            now=lambda: FIXED_NOW,
        )

        self.assertTrue(
            result["queued"]
        )
        self.assertEqual(
            result["delivery_id"],
            "delivery-1",
        )
        self.assertEqual(
            result["transition_count"],
            1,
        )

        rows = self.read_rows()

        self.assertEqual(
            len(
                rows
            ),
            1,
        )

        row = rows[0]
        expected_timestamp = (
            FIXED_NOW.isoformat()
        )

        self.assertEqual(
            row["state"],
            "pending",
        )
        self.assertEqual(
            row["attempt_count"],
            0,
        )
        self.assertEqual(
            row["max_attempts"],
            5,
        )
        self.assertEqual(
            row["next_attempt_at"],
            expected_timestamp,
        )
        self.assertIsNone(
            row["claimed_at"]
        )
        self.assertIsNone(
            row["claim_token"]
        )
        self.assertEqual(
            row["created_at"],
            expected_timestamp,
        )
        self.assertEqual(
            row["updated_at"],
            expected_timestamp,
        )
        self.assertIsNone(
            row["completed_at"]
        )

        payload = json.loads(
            row["payload_json"]
        )

        self.assertEqual(
            payload["transition_count"],
            1,
        )
        self.assertEqual(
            payload["sent_at"],
            expected_timestamp,
        )

        serialized = row["payload_json"]

        for forbidden in (
            self.enabled_settings.webhook_url,
            "authorization",
            "password",
            "secret",
            "traceback",
            "exception",
        ):
            self.assertNotIn(
                forbidden,
                serialized.casefold(),
            )

    def test_payload_serialization_is_deterministic(
        self,
    ):
        for delivery_id in (
            "delivery-a",
            "delivery-b",
        ):
            enqueue_system_incident_alert(
                self.enabled_settings,
                opened_evaluation(),
                db_path=str(
                    self.database_path
                ),
                delivery_id_factory=(
                    lambda value=delivery_id: value
                ),
                now=lambda: FIXED_NOW,
            )

        rows = self.read_rows()

        self.assertEqual(
            rows[0]["payload_json"],
            rows[1]["payload_json"],
        )

    def test_max_attempt_bounds_are_persisted(
        self,
    ):
        for max_attempts in (
            1,
            10,
        ):
            enqueue_system_incident_alert(
                self.enabled_settings,
                opened_evaluation(),
                db_path=str(
                    self.database_path
                ),
                delivery_id_factory=(
                    lambda value=max_attempts: (
                        "delivery-"
                        + str(
                            value
                        )
                    )
                ),
                now=lambda: FIXED_NOW,
                max_attempts=max_attempts,
            )

        rows = self.read_rows()

        self.assertEqual(
            [
                row["max_attempts"]
                for row in rows
            ],
            [
                1,
                10,
            ],
        )

    def test_invalid_max_attempts_are_rejected_without_write(
        self,
    ):
        for invalid in (
            0,
            11,
            True,
            "5",
        ):
            with self.subTest(
                invalid=invalid
            ):
                connection_factory = MagicMock(
                    side_effect=AssertionError(
                        "connection must not be opened"
                    )
                )

                with self.assertRaises(
                    SystemIncidentAlertOutboxError
                ):
                    enqueue_system_incident_alert(
                        self.enabled_settings,
                        opened_evaluation(),
                        connection_factory=(
                            connection_factory
                        ),
                        max_attempts=invalid,
                    )

                connection_factory.assert_not_called()

        self.assertEqual(
            self.read_rows(),
            [],
        )

    def test_invalid_delivery_id_is_rejected_without_write(
        self,
    ):
        for invalid in (
            "",
            "x" * 129,
        ):
            with self.subTest(
                length=len(
                    invalid
                )
            ):
                connection_factory = MagicMock(
                    side_effect=AssertionError(
                        "connection must not be opened"
                    )
                )

                with self.assertRaises(
                    SystemIncidentAlertOutboxError
                ):
                    enqueue_system_incident_alert(
                        self.enabled_settings,
                        opened_evaluation(),
                        connection_factory=(
                            connection_factory
                        ),
                        delivery_id_factory=(
                            lambda value=invalid: value
                        ),
                        now=lambda: FIXED_NOW,
                    )

                connection_factory.assert_not_called()

        self.assertEqual(
            self.read_rows(),
            [],
        )

    def test_oversized_payload_is_rejected_without_write(
        self,
    ):
        connection_factory = MagicMock(
            side_effect=AssertionError(
                "connection must not be opened"
            )
        )

        oversized = {
            "service": "system_incidents",
            "event": "incident_transitions",
            "payload": (
                "x"
                * (
                    MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES
                    + 1
                )
            ),
        }

        with patch(
            (
                "app.services."
                "system_incident_alert_outbox_service."
                "build_system_incident_alert_payload"
            ),
            return_value=oversized,
        ):
            with self.assertRaises(
                SystemIncidentAlertOutboxError
            ):
                enqueue_system_incident_alert(
                    self.enabled_settings,
                    opened_evaluation(),
                    connection_factory=(
                        connection_factory
                    ),
                    now=lambda: FIXED_NOW,
                )

        connection_factory.assert_not_called()
        self.assertEqual(
            self.read_rows(),
            [],
        )

    def test_builder_failure_is_generic_and_opens_no_connection(
        self,
    ):
        connection_factory = MagicMock(
            side_effect=AssertionError(
                "connection must not be opened"
            )
        )

        with patch(
            (
                "app.services."
                "system_incident_alert_outbox_service."
                "build_system_incident_alert_payload"
            ),
            side_effect=RuntimeError(
                "secret-token-value"
            ),
        ):
            with self.assertRaises(
                SystemIncidentAlertOutboxError
            ) as captured:
                enqueue_system_incident_alert(
                    self.enabled_settings,
                    opened_evaluation(),
                    connection_factory=(
                        connection_factory
                    ),
                    now=lambda: FIXED_NOW,
                )

        self.assertNotIn(
            "secret-token-value",
            str(
                captured.exception
            ),
        )
        connection_factory.assert_not_called()

    def test_insert_failure_rolls_back_and_closes(
        self,
    ):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = RuntimeError(
            "database contains secret"
        )

        with self.assertRaises(
            SystemIncidentAlertOutboxError
        ) as captured:
            enqueue_system_incident_alert(
                self.enabled_settings,
                opened_evaluation(),
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    lambda _path: connection
                ),
                delivery_id_factory=(
                    lambda: "delivery-failure"
                ),
                now=lambda: FIXED_NOW,
            )

        self.assertEqual(
            str(
                captured.exception
            ),
            "System incident alert outbox write failed.",
        )
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()
        self.assertNotIn(
            "secret",
            str(
                captured.exception
            ),
        )

    def test_duplicate_delivery_id_rolls_back_without_data_loss(
        self,
    ):
        enqueue_system_incident_alert(
            self.enabled_settings,
            opened_evaluation(),
            db_path=str(
                self.database_path
            ),
            delivery_id_factory=(
                lambda: "delivery-duplicate"
            ),
            now=lambda: FIXED_NOW,
        )

        with self.assertRaises(
            SystemIncidentAlertOutboxError
        ):
            enqueue_system_incident_alert(
                self.enabled_settings,
                opened_evaluation(),
                db_path=str(
                    self.database_path
                ),
                delivery_id_factory=(
                    lambda: "delivery-duplicate"
                ),
                now=lambda: FIXED_NOW,
            )

        rows = self.read_rows()

        self.assertEqual(
            len(
                rows
            ),
            1,
        )
        self.assertEqual(
            rows[0]["delivery_id"],
            "delivery-duplicate",
        )

    def test_naive_clock_is_normalized_to_utc(
        self,
    ):
        naive_now = datetime(
            2026,
            7,
            22,
            10,
            30,
            0,
        )

        enqueue_system_incident_alert(
            self.enabled_settings,
            opened_evaluation(),
            db_path=str(
                self.database_path
            ),
            delivery_id_factory=(
                lambda: "delivery-naive"
            ),
            now=lambda: naive_now,
        )

        row = self.read_rows()[0]

        self.assertEqual(
            row["created_at"],
            "2026-07-22T10:30:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
