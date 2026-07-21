from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import (
    func,
    select,
)

from app.config.database import (
    DatabaseSettings,
)
from app.database.db import (
    get_runtime_connection,
)
from app.database.engine import (
    build_database_engine,
)
from app.database.migrations import (
    initialize_schema,
)
from app.database.schema import (
    document_recovery_runs,
)
from app.services.document_recovery_history_service import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_RETENTION_LIMIT,
    MAX_HISTORY_LIMIT,
    DocumentRecoveryHistoryError,
    list_document_recovery_runs,
    record_document_recovery_run,
    summarize_document_recovery_runs,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
)


def completed_report(
    *,
    status: str = "completed",
    failure_count: int = 0,
    error: str | None = None,
):
    return DocumentRecoveryStartupReport(
        status=status,
        enabled=True,
        total_examined=4,
        candidate_count=2,
        processing_recovered_count=1,
        deleting_completed_count=1,
        failure_count=failure_count,
        skipped_count=0,
        recent_count=2,
        invalid_timestamp_count=0,
        deferred_count=0,
        error=error,
    )


class DocumentRecoveryHistoryServiceTests(
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
            / "history-service.db"
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

        self.connection_factory = (
            lambda ignored_path: (
                get_runtime_connection(
                    str(
                        self.database_path
                    ),
                    environ={},
                )
            )
        )

    def tearDown(self):
        self.engine.dispose()

        self.temporary_directory.cleanup()

    def record(
        self,
        *,
        run_id: str,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        report=None,
        retention_limit: int = (
            DEFAULT_RETENTION_LIMIT
        ),
    ):
        return record_document_recovery_run(
            (
                completed_report()
                if report is None
                else report
            ),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
            run_id_factory=lambda: run_id,
            retention_limit=retention_limit,
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

    def test_record_and_list_are_sanitized(
        self,
    ):
        stored = self.record(
            run_id="run-safe",
            started_at=(
                "2026-07-21T10:00:00Z"
            ),
            finished_at=(
                "2026-07-21T10:00:01Z"
            ),
            duration_ms=1000,
            report=completed_report(
                error=(
                    "SECRET filename.pdf "
                    "document-id-123"
                )
            ),
        )

        self.assertEqual(
            stored["run_id"],
            "run-safe",
        )

        self.assertTrue(
            stored["recovery_enabled"]
        )

        self.assertNotIn(
            "error",
            stored,
        )

        rows = list_document_recovery_runs(
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

        self.assertEqual(
            len(rows),
            1,
        )

        self.assertEqual(
            rows[0]["status"],
            "completed",
        )

        self.assertNotIn(
            "error",
            rows[0],
        )

        serialized = repr(rows)

        self.assertNotIn(
            "SECRET",
            serialized,
        )

        self.assertNotIn(
            "filename.pdf",
            serialized,
        )

        self.assertNotIn(
            "document-id-123",
            serialized,
        )

    def test_history_is_newest_first(
        self,
    ):
        self.record(
            run_id="run-old",
            started_at=(
                "2026-07-21T10:00:00Z"
            ),
            finished_at=(
                "2026-07-21T10:00:01Z"
            ),
            duration_ms=1000,
        )

        self.record(
            run_id="run-new",
            started_at=(
                "2026-07-21T11:00:00Z"
            ),
            finished_at=(
                "2026-07-21T11:00:01Z"
            ),
            duration_ms=1000,
        )

        rows = list_document_recovery_runs(
            2,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

        self.assertEqual(
            [
                row["run_id"]
                for row in rows
            ],
            [
                "run-new",
                "run-old",
            ],
        )

    def test_retention_keeps_newest_rows(
        self,
    ):
        for index in range(5):
            self.record(
                run_id=f"run-{index}",
                started_at=(
                    "2026-07-21T"
                    f"10:00:0{index}+00:00"
                ),
                finished_at=(
                    "2026-07-21T"
                    f"10:00:0{index}+00:00"
                ),
                duration_ms=index,
                retention_limit=3,
            )

        rows = list_document_recovery_runs(
            3,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

        self.assertEqual(
            [
                row["run_id"]
                for row in rows
            ],
            [
                "run-4",
                "run-3",
                "run-2",
            ],
        )

        with self.engine.connect() as connection:
            count = connection.execute(
                select(
                    func.count()
                ).select_from(
                    document_recovery_runs
                )
            ).scalar_one()

        self.assertEqual(
            int(count),
            3,
        )

    def test_summary_returns_operational_metrics(
        self,
    ):
        self.record(
            run_id="run-complete",
            started_at=(
                "2026-07-21T10:00:00Z"
            ),
            finished_at=(
                "2026-07-21T10:00:01Z"
            ),
            duration_ms=1000,
        )

        self.record(
            run_id="run-failed",
            started_at=(
                "2026-07-21T11:00:00Z"
            ),
            finished_at=(
                "2026-07-21T11:00:03Z"
            ),
            duration_ms=3000,
            report=completed_report(
                status="failed",
                failure_count=1,
                error="private exception",
            ),
        )

        summary = (
            summarize_document_recovery_runs(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
            )
        )

        self.assertEqual(
            summary["total_runs"],
            2,
        )

        self.assertEqual(
            summary["status_counts"][
                "completed"
            ],
            1,
        )

        self.assertEqual(
            summary["status_counts"][
                "failed"
            ],
            1,
        )

        self.assertEqual(
            summary["failure_runs"],
            1,
        )

        self.assertEqual(
            summary["total_failures"],
            1,
        )

        self.assertEqual(
            summary[
                "average_duration_ms"
            ],
            2000.0,
        )

        self.assertEqual(
            summary["latest_run"][
                "run_id"
            ],
            "run-failed",
        )

        self.assertNotIn(
            "error",
            repr(summary),
        )

    def test_empty_summary_is_stable(
        self,
    ):
        summary = (
            summarize_document_recovery_runs(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
            )
        )

        self.assertEqual(
            summary["total_runs"],
            0,
        )

        self.assertEqual(
            summary["failure_runs"],
            0,
        )

        self.assertEqual(
            summary["total_failures"],
            0,
        )

        self.assertEqual(
            summary[
                "average_duration_ms"
            ],
            0.0,
        )

        self.assertIsNone(
            summary["latest_run"]
        )

    def test_invalid_status_is_rejected(
        self,
    ):
        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="invalid-status",
                started_at=(
                    "2026-07-21T10:00:00Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
                report=completed_report(
                    status="secret-custom-state",
                ),
            )

    def test_negative_metrics_are_rejected(
        self,
    ):
        invalid_report = {
            "status": "completed",
            "enabled": True,
            "failure_count": -1,
        }

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="negative-count",
                started_at=(
                    "2026-07-21T10:00:00Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
                report=invalid_report,
            )

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="negative-duration",
                started_at=(
                    "2026-07-21T10:00:00Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=-1,
            )

    def test_invalid_timestamps_are_rejected(
        self,
    ):
        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="invalid-time",
                started_at="not-a-time",
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
            )

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="reversed-time",
                started_at=(
                    "2026-07-21T10:00:02Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
            )

    def test_limits_are_bounded(
        self,
    ):
        for invalid_limit in (
            0,
            -1,
            101,
            True,
        ):
            with self.subTest(
                invalid_limit=invalid_limit
            ):
                with self.assertRaises(
                    DocumentRecoveryHistoryError
                ):
                    list_document_recovery_runs(
                        invalid_limit,
                        db_path=str(
                            self.database_path
                        ),
                        connection_factory=(
                            self.connection_factory
                        ),
                    )

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ):
            self.record(
                run_id="invalid-retention",
                started_at=(
                    "2026-07-21T10:00:00Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
                retention_limit=101,
            )

    def test_write_failure_is_generic_and_rolls_back(
        self,
    ):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        cursor.execute.side_effect = [
            None,
            RuntimeError(
                "SECRET database path"
            ),
        ]

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ) as caught:
            record_document_recovery_run(
                completed_report(),
                started_at=(
                    "2026-07-21T10:00:00Z"
                ),
                finished_at=(
                    "2026-07-21T10:00:01Z"
                ),
                duration_ms=1000,
                connection_factory=(
                    lambda ignored_path: connection
                ),
                run_id_factory=(
                    lambda: "rollback-run"
                ),
            )

        self.assertEqual(
            str(caught.exception),
            (
                "Document recovery history "
                "write failed."
            ),
        )

        self.assertNotIn(
            "SECRET",
            str(caught.exception),
        )

        connection.rollback.assert_called()
        connection.close.assert_called()

    def test_read_failure_is_generic(
        self,
    ):
        def failing_factory(
            ignored_path,
        ):
            raise RuntimeError(
                "SECRET connection value"
            )

        with self.assertRaises(
            DocumentRecoveryHistoryError
        ) as caught:
            list_document_recovery_runs(
                connection_factory=(
                    failing_factory
                ),
            )

        self.assertEqual(
            str(caught.exception),
            (
                "Document recovery history "
                "read failed."
            ),
        )

        self.assertNotIn(
            "SECRET",
            str(caught.exception),
        )

    def test_datetime_values_are_normalized_to_utc(
        self,
    ):
        stored = record_document_recovery_run(
            completed_report(),
            started_at=datetime(
                2026,
                7,
                21,
                10,
                0,
                0,
                tzinfo=timezone.utc,
            ),
            finished_at=datetime(
                2026,
                7,
                21,
                10,
                0,
                1,
                tzinfo=timezone.utc,
            ),
            duration_ms=1000,
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
            run_id_factory=(
                lambda: "datetime-run"
            ),
        )

        self.assertEqual(
            stored["started_at"],
            "2026-07-21T10:00:00+00:00",
        )

        self.assertEqual(
            stored["finished_at"],
            "2026-07-21T10:00:01+00:00",
        )


if __name__ == "__main__":
    unittest.main()
