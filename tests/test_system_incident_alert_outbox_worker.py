from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

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
    enqueue_system_incident_alert,
)
from app.services.system_incident_alert_outbox_worker import (
    SystemIncidentAlertOutboxWorkerError,
    claim_due_system_incident_alert,
    complete_claimed_system_incident_alert,
    compute_system_incident_alert_backoff_seconds,
    process_next_system_incident_alert,
    recover_stale_system_incident_alert_claims,
    retry_or_fail_claimed_system_incident_alert,
)


BASE_NOW = datetime(
    2026,
    7,
    22,
    11,
    0,
    0,
    tzinfo=timezone.utc,
)


def opened_evaluation() -> dict:
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T10:59:00+00:00"
        ),
        "opened": [
            {
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
        ],
        "updated": [],
        "resolved": [],
        "unchanged": [],
    }


class SystemIncidentAlertOutboxWorkerTests(
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
            / "alert-worker.db"
        )

        engine = build_database_engine(
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
            engine
        )
        engine.dispose()

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

    def enqueue(
        self,
        delivery_id: str = "delivery-1",
        *,
        max_attempts: int = 5,
        now: datetime = BASE_NOW,
    ):
        return enqueue_system_incident_alert(
            self.enabled_settings,
            opened_evaluation(),
            db_path=str(
                self.database_path
            ),
            delivery_id_factory=(
                lambda: delivery_id
            ),
            now=lambda: now,
            max_attempts=max_attempts,
        )

    def read_row(
        self,
        delivery_id: str = "delivery-1",
    ):
        connection = sqlite3.connect(
            self.database_path
        )
        connection.row_factory = sqlite3.Row

        try:
            return connection.execute(
                """
                SELECT *
                FROM system_incident_alert_outbox
                WHERE delivery_id = ?
                """,
                (
                    delivery_id,
                ),
            ).fetchone()
        finally:
            connection.close()

    def test_disabled_worker_opens_no_connection(
        self,
    ):
        connection_factory = MagicMock(
            side_effect=AssertionError(
                "connection must not open"
            )
        )

        result = process_next_system_incident_alert(
            self.disabled_settings,
            connection_factory=(
                connection_factory
            ),
        )

        self.assertFalse(
            result["enabled"]
        )
        self.assertFalse(
            result["attempted"]
        )
        connection_factory.assert_not_called()

    def test_idle_worker_returns_without_attempt(
        self,
    ):
        sender = MagicMock()

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=sender,
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-idle"
            ),
        )

        self.assertEqual(
            result["state"],
            "idle",
        )
        sender.assert_not_called()

    def test_claim_sets_processing_and_increments_attempt(
        self,
    ):
        self.enqueue()

        claim = claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-1"
            ),
            now=lambda: BASE_NOW,
        )

        self.assertEqual(
            claim["delivery_id"],
            "delivery-1",
        )
        self.assertEqual(
            claim["attempt_count"],
            1,
        )
        self.assertEqual(
            claim["claim_token"],
            "claim-1",
        )

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "processing",
        )
        self.assertEqual(
            row["attempt_count"],
            1,
        )
        self.assertEqual(
            row["claim_token"],
            "claim-1",
        )

    def test_claim_is_exclusive(
        self,
    ):
        self.enqueue()

        first = claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-first"
            ),
            now=lambda: BASE_NOW,
        )

        second = claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-second"
            ),
            now=lambda: BASE_NOW,
        )

        self.assertIsNotNone(
            first
        )
        self.assertIsNone(
            second
        )

    def test_successful_delivery_marks_completed(
        self,
    ):
        self.enqueue()
        sender = MagicMock()

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=sender,
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-success"
            ),
        )

        self.assertEqual(
            result["state"],
            "completed",
        )
        sender.assert_called_once()

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "completed",
        )
        self.assertEqual(
            row["claim_token"],
            "claim-success",
        )
        self.assertEqual(
            row["completed_at"],
            BASE_NOW.isoformat(),
        )

        sent_url, sent_payload, timeout = (
            sender.call_args.args
        )

        self.assertEqual(
            sent_url,
            self.enabled_settings.webhook_url,
        )
        self.assertIsInstance(
            sent_payload,
            dict,
        )
        self.assertEqual(
            timeout,
            2,
        )

    def test_completion_is_idempotent_by_claim_token(
        self,
    ):
        self.enqueue()

        claim = claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-complete"
            ),
            now=lambda: BASE_NOW,
        )

        first = complete_claimed_system_incident_alert(
            claim["delivery_id"],
            claim["claim_token"],
            db_path=str(
                self.database_path
            ),
            now=lambda: BASE_NOW,
        )

        second = complete_claimed_system_incident_alert(
            claim["delivery_id"],
            claim["claim_token"],
            db_path=str(
                self.database_path
            ),
            now=lambda: BASE_NOW,
        )

        self.assertTrue(
            first
        )
        self.assertFalse(
            second
        )

    def test_retry_failure_returns_pending_with_backoff(
        self,
    ):
        self.enqueue(
            max_attempts=3
        )

        sender = MagicMock(
            side_effect=RuntimeError(
                "secret provider response"
            )
        )

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=sender,
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-retry"
            ),
        )

        self.assertEqual(
            result["state"],
            "pending",
        )

        expected_next = (
            BASE_NOW
            + timedelta(
                seconds=30
            )
        ).isoformat()

        self.assertEqual(
            result["next_attempt_at"],
            expected_next,
        )

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "pending",
        )
        self.assertEqual(
            row["attempt_count"],
            1,
        )
        self.assertEqual(
            row["next_attempt_at"],
            expected_next,
        )
        self.assertIsNone(
            row["claimed_at"]
        )
        self.assertIsNone(
            row["claim_token"]
        )
        self.assertNotIn(
            "secret",
            row["payload_json"],
        )

    def test_retry_is_not_claimed_before_due_time(
        self,
    ):
        self.enqueue(
            max_attempts=3
        )

        process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=MagicMock(
                side_effect=RuntimeError(
                    "temporary"
                )
            ),
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-first"
            ),
        )

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=MagicMock(),
            now=lambda: (
                BASE_NOW
                + timedelta(
                    seconds=29
                )
            ),
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-early"
            ),
        )

        self.assertEqual(
            result["state"],
            "idle",
        )

    def test_final_failure_marks_terminal_failed(
        self,
    ):
        self.enqueue(
            max_attempts=1
        )

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=MagicMock(
                side_effect=RuntimeError(
                    "provider body"
                )
            ),
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-final"
            ),
        )

        self.assertEqual(
            result["state"],
            "failed",
        )

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "failed",
        )
        self.assertEqual(
            row["attempt_count"],
            1,
        )
        self.assertEqual(
            row["claim_token"],
            "claim-final",
        )
        self.assertEqual(
            row["completed_at"],
            BASE_NOW.isoformat(),
        )

    def test_malformed_payload_is_terminal_without_sender(
        self,
    ):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            timestamp = BASE_NOW.isoformat()

            connection.execute(
                """
                INSERT INTO system_incident_alert_outbox (
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
                )
                VALUES (
                    ?, ?,
                    'pending',
                    0, 1,
                    ?,
                    NULL,
                    NULL,
                    ?,
                    ?,
                    NULL
                )
                """,
                (
                    "delivery-invalid",
                    "{}",
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )

            connection.commit()
        finally:
            connection.close()

        sender = MagicMock()

        result = process_next_system_incident_alert(
            self.enabled_settings,
            db_path=str(
                self.database_path
            ),
            sender=sender,
            now=lambda: BASE_NOW,
            jitter=lambda: 0.0,
            claim_token_factory=(
                lambda: "claim-invalid"
            ),
        )

        self.assertEqual(
            result["state"],
            "failed",
        )
        sender.assert_not_called()

        row = self.read_row(
            "delivery-invalid"
        )

        self.assertEqual(
            row["state"],
            "failed",
        )

    def test_stale_claim_is_recovered_to_pending(
        self,
    ):
        self.enqueue(
            max_attempts=3
        )

        claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-stale"
            ),
            now=lambda: BASE_NOW,
        )

        recovery_now = (
            BASE_NOW
            + timedelta(
                seconds=120
            )
        )

        result = (
            recover_stale_system_incident_alert_claims(
                stale_after_seconds=60,
                db_path=str(
                    self.database_path
                ),
                now=lambda: recovery_now,
            )
        )

        self.assertEqual(
            result,
            {
                "recovered_count": 1,
                "failed_count": 0,
            },
        )

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "pending",
        )
        self.assertEqual(
            row["attempt_count"],
            1,
        )
        self.assertEqual(
            row["next_attempt_at"],
            recovery_now.isoformat(),
        )
        self.assertIsNone(
            row["claim_token"]
        )

    def test_recent_claim_is_not_recovered(
        self,
    ):
        self.enqueue()

        claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-recent"
            ),
            now=lambda: BASE_NOW,
        )

        result = (
            recover_stale_system_incident_alert_claims(
                stale_after_seconds=60,
                db_path=str(
                    self.database_path
                ),
                now=lambda: (
                    BASE_NOW
                    + timedelta(
                        seconds=30
                    )
                ),
            )
        )

        self.assertEqual(
            result,
            {
                "recovered_count": 0,
                "failed_count": 0,
            },
        )

        self.assertEqual(
            self.read_row()["state"],
            "processing",
        )

    def test_backoff_is_bounded_and_jittered(
        self,
    ):
        self.assertEqual(
            compute_system_incident_alert_backoff_seconds(
                1,
                jitter_value=0.0,
            ),
            30.0,
        )

        self.assertEqual(
            compute_system_incident_alert_backoff_seconds(
                2,
                jitter_value=1.0,
            ),
            75.0,
        )

        self.assertEqual(
            compute_system_incident_alert_backoff_seconds(
                20,
                jitter_value=1.0,
            ),
            3600.0,
        )

    def test_invalid_jitter_is_rejected_before_claim(
        self,
    ):
        self.enqueue()

        with self.assertRaises(
            SystemIncidentAlertOutboxWorkerError
        ):
            process_next_system_incident_alert(
                self.enabled_settings,
                db_path=str(
                    self.database_path
                ),
                sender=MagicMock(),
                now=lambda: BASE_NOW,
                jitter=lambda: 2.0,
                claim_token_factory=(
                    lambda: "claim-invalid-jitter"
                ),
            )

        row = self.read_row()

        self.assertEqual(
            row["state"],
            "pending",
        )
        self.assertEqual(
            row["attempt_count"],
            0,
        )

    def test_retry_update_requires_matching_claim_token(
        self,
    ):
        self.enqueue(
            max_attempts=3
        )

        claim = claim_due_system_incident_alert(
            db_path=str(
                self.database_path
            ),
            claim_token_factory=(
                lambda: "claim-real"
            ),
            now=lambda: BASE_NOW,
        )

        result = (
            retry_or_fail_claimed_system_incident_alert(
                claim["delivery_id"],
                "claim-wrong",
                attempt_count=1,
                max_attempts=3,
                jitter_value=0.0,
                db_path=str(
                    self.database_path
                ),
                now=lambda: BASE_NOW,
            )
        )

        self.assertFalse(
            result["updated"]
        )
        self.assertEqual(
            self.read_row()["state"],
            "processing",
        )

    def test_claim_database_failure_is_generic_and_safe(
        self,
    ):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = RuntimeError(
            "database secret"
        )

        with self.assertRaises(
            SystemIncidentAlertOutboxWorkerError
        ) as captured:
            claim_due_system_incident_alert(
                connection_factory=(
                    lambda _path: connection
                ),
                claim_token_factory=(
                    lambda: "claim-db-error"
                ),
                now=lambda: BASE_NOW,
            )

        self.assertEqual(
            str(
                captured.exception
            ),
            "System incident alert outbox claim failed.",
        )
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()
        self.assertNotIn(
            "secret",
            str(
                captured.exception
            ),
        )


if __name__ == "__main__":
    unittest.main()
