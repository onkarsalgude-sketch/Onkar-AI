from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.api.document_recovery_admin import (
    _report_payload,
)
from app.config.database import (
    DatabaseSettings,
)
from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_recovery_lock import (
    DOCUMENT_RECOVERY_ADVISORY_LOCK_ID,
    document_recovery_lock,
    try_acquire_document_recovery_lock,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
    run_document_recovery_startup,
)


def sqlite_settings(
    database_path: Path,
) -> DatabaseSettings:
    return DatabaseSettings(
        backend="sqlite",
        database_url=None,
        sqlite_path=database_path,
        require_persistence=False,
        pool_size=5,
        connect_timeout_seconds=10,
    )


def postgresql_settings(
) -> DatabaseSettings:
    return DatabaseSettings(
        backend="postgresql",
        database_url=(
            "postgresql+psycopg://"
            "user:password@localhost/database"
        ),
        sqlite_path=Path("unused.db"),
        require_persistence=True,
        pool_size=5,
        connect_timeout_seconds=10,
    )


def settings_loader(
    settings: DatabaseSettings,
):
    def load(
        environ=None,
        *,
        default_sqlite_path=None,
    ):
        return settings

    return load


class FakeCursor:
    def __init__(
        self,
        row,
    ):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(
        self,
        acquired: bool,
    ):
        self.acquired = acquired
        self.executed = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def execute(
        self,
        sql,
        parameters=None,
    ):
        self.executed.append(
            (
                sql,
                parameters,
            )
        )

        if "pg_try_advisory_lock" in sql:
            return FakeCursor(
                (
                    self.acquired,
                )
            )

        if "pg_advisory_unlock" in sql:
            return FakeCursor(
                (
                    True,
                )
            )

        raise AssertionError(
            f"Unexpected SQL: {sql}"
        )

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


def empty_recovery_run():
    return SimpleNamespace(
        scan=SimpleNamespace(
            total_examined=0,
            candidate_count=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
        ),
        processing_recovered_count=0,
        deleting_completed_count=0,
        failure_count=0,
        skipped_count=0,
    )


@contextmanager
def fake_lock_context(
    acquired: bool,
):
    yield SimpleNamespace(
        acquired=acquired,
        backend="test",
    )


class DocumentRecoverySQLiteLockTests(
    unittest.TestCase
):
    def test_second_sqlite_instance_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "recovery.db"
            )

            settings = sqlite_settings(
                database_path
            )

            first = (
                try_acquire_document_recovery_lock(
                    settings_loader=(
                        settings_loader(
                            settings
                        )
                    )
                )
            )

            self.assertTrue(
                first.acquired
            )

            try:
                second = (
                    try_acquire_document_recovery_lock(
                        settings_loader=(
                            settings_loader(
                                settings
                            )
                        )
                    )
                )

                self.assertFalse(
                    second.acquired
                )

                second.release()
            finally:
                first.release()

    def test_sqlite_lock_can_be_reacquired_after_release(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            settings = sqlite_settings(
                Path(directory)
                / "recovery.db"
            )

            first = (
                try_acquire_document_recovery_lock(
                    settings_loader=(
                        settings_loader(
                            settings
                        )
                    )
                )
            )

            self.assertTrue(
                first.acquired
            )

            first.release()

            second = (
                try_acquire_document_recovery_lock(
                    settings_loader=(
                        settings_loader(
                            settings
                        )
                    )
                )
            )

            try:
                self.assertTrue(
                    second.acquired
                )
            finally:
                second.release()


class DocumentRecoveryPostgreSQLLockTests(
    unittest.TestCase
):
    def test_postgresql_lock_uses_session_advisory_lock(
        self,
    ):
        connection = FakeConnection(
            acquired=True
        )

        lease = (
            try_acquire_document_recovery_lock(
                settings_loader=(
                    settings_loader(
                        postgresql_settings()
                    )
                ),
                connection_factory=Mock(
                    return_value=connection
                ),
            )
        )

        self.assertTrue(
            lease.acquired
        )

        self.assertFalse(
            connection.closed
        )

        self.assertEqual(
            connection.executed[0],
            (
                "SELECT pg_try_advisory_lock(?)",
                (
                    DOCUMENT_RECOVERY_ADVISORY_LOCK_ID,
                ),
            ),
        )

        lease.release()

        self.assertTrue(
            connection.closed
        )

        self.assertEqual(
            connection.commit_count,
            2,
        )

        self.assertIn(
            "pg_advisory_unlock",
            connection.executed[1][0],
        )

    def test_postgresql_contention_closes_connection(
        self,
    ):
        connection = FakeConnection(
            acquired=False
        )

        lease = (
            try_acquire_document_recovery_lock(
                settings_loader=(
                    settings_loader(
                        postgresql_settings()
                    )
                ),
                connection_factory=Mock(
                    return_value=connection
                ),
            )
        )

        self.assertFalse(
            lease.acquired
        )

        self.assertTrue(
            connection.closed
        )

        self.assertEqual(
            len(connection.executed),
            1,
        )


class DocumentRecoveryRuntimeLockTests(
    unittest.TestCase
):
    def test_contention_skips_scan_and_recovery(
        self,
    ):
        recover_fn = Mock()

        report = (
            run_document_recovery_startup(
                rag=object(),
                settings=(
                    DocumentRecoverySettings(
                        enabled=True,
                        stale_after_seconds=900,
                        batch_size=25,
                    )
                ),
                recover_fn=recover_fn,
                lock_context_factory=(
                    lambda: fake_lock_context(
                        False
                    )
                ),
            )
        )

        recover_fn.assert_not_called()

        self.assertEqual(
            report.status,
            "skipped_lock_held",
        )

        self.assertEqual(
            report.failure_count,
            0,
        )

        self.assertTrue(
            report.enabled
        )

    def test_acquired_lock_runs_recovery(
        self,
    ):
        recover_fn = Mock(
            return_value=empty_recovery_run()
        )

        report = (
            run_document_recovery_startup(
                rag=object(),
                settings=(
                    DocumentRecoverySettings(
                        enabled=True,
                        stale_after_seconds=900,
                        batch_size=25,
                    )
                ),
                recover_fn=recover_fn,
                lock_context_factory=(
                    lambda: fake_lock_context(
                        True
                    )
                ),
            )
        )

        recover_fn.assert_called_once()

        self.assertEqual(
            report.status,
            "completed",
        )

    def test_lock_failure_is_non_fatal(
        self,
    ):
        def failing_lock():
            raise RuntimeError(
                "Temporary lock service failure"
            )

        report = (
            run_document_recovery_startup(
                rag=object(),
                settings=(
                    DocumentRecoverySettings(
                        enabled=True,
                        stale_after_seconds=900,
                        batch_size=25,
                    )
                ),
                recover_fn=Mock(),
                lock_context_factory=(
                    failing_lock
                ),
            )
        )

        self.assertEqual(
            report.status,
            "failed",
        )

        self.assertEqual(
            report.failure_count,
            1,
        )


class DocumentRecoveryMonitoringLockTests(
    unittest.TestCase
):
    def test_lock_contention_is_reported_as_healthy(
        self,
    ):
        report = DocumentRecoveryStartupReport(
            status="skipped_lock_held",
            enabled=True,
            total_examined=0,
            candidate_count=0,
            processing_recovered_count=0,
            deleting_completed_count=0,
            failure_count=0,
            skipped_count=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
        )

        payload = _report_payload(
            report
        )

        self.assertTrue(
            payload["ready"]
        )

        self.assertTrue(
            payload["healthy"]
        )

        self.assertFalse(
            payload["attention_required"]
        )

        self.assertEqual(
            payload["status"],
            "skipped_lock_held",
        )


if __name__ == "__main__":
    unittest.main()
