import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import (
    DATABASE_OPERATIONAL_ERRORS,
    PortableConnection,
    acquire_branch_merge_lock,
    configure_busy_timeout,
    get_runtime_connection,
    is_database_busy_error,
)
from app.services import branch_merge_service


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed
        self.description = None
        self.rowcount = 0
        self.lastrowid = None

    def execute(
        self,
        sql,
        parameters=None,
    ):
        self.executed.append(
            (sql, parameters)
        )

    def close(self):
        return None


class FakeRawConnection:
    def __init__(self):
        self.executed = []

    def cursor(self):
        return FakeCursor(
            self.executed
        )

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class PostgreSQLBusyError(Exception):
    sqlstate = "55P03"


class BranchMergeDatabasePortabilityTests(
    unittest.TestCase
):
    def test_service_uses_runtime_connection_adapter(
        self,
    ):
        self.assertIs(
            branch_merge_service.get_connection,
            get_runtime_connection,
        )

    def test_sqlite_busy_timeout_is_configured(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "busy.db"
            )

            connection = sqlite3.connect(
                database_path
            )

            try:
                configure_busy_timeout(
                    connection,
                    4321,
                )

                value = connection.execute(
                    "PRAGMA busy_timeout"
                ).fetchone()[0]

                self.assertEqual(
                    value,
                    4321,
                )
            finally:
                connection.close()

    def test_postgresql_merge_lock_uses_advisory_lock(
        self,
    ):
        raw = FakeRawConnection()
        connection = PortableConnection(raw)

        acquire_branch_merge_lock(
            connection
        )

        self.assertEqual(
            len(raw.executed),
            1,
        )
        self.assertIn(
            "pg_advisory_xact_lock",
            raw.executed[0][0],
        )
        self.assertEqual(
            raw.executed[0][1],
            (752024,),
        )

    def test_busy_detection_supports_both_databases(
        self,
    ):
        self.assertTrue(
            is_database_busy_error(
                sqlite3.OperationalError(
                    "database is locked"
                )
            )
        )

        self.assertTrue(
            is_database_busy_error(
                PostgreSQLBusyError()
            )
        )

        self.assertIn(
            sqlite3.OperationalError,
            DATABASE_OPERATIONAL_ERRORS,
        )

    def test_execute_branch_merge_has_no_sqlite_transaction_sql(
        self,
    ):
        source = inspect.getsource(
            branch_merge_service
            .execute_branch_merge
        )

        self.assertNotIn(
            "PRAGMA busy_timeout",
            source,
        )
        self.assertNotIn(
            "BEGIN IMMEDIATE",
            source,
        )
        self.assertIn(
            "begin_write_transaction",
            source,
        )
        self.assertIn(
            "acquire_branch_merge_lock",
            source,
        )


if __name__ == "__main__":
    unittest.main()
