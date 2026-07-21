from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import (
    inspect,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError

from app.config.database import (
    DatabaseSettings,
)
from app.database import (
    data_migration,
)
from app.database.engine import (
    build_database_engine,
)
from app.database.migrations import (
    SchemaCompatibilityError,
    _SCHEMA_V1_APPLICATION_TABLES,
    get_schema_version,
    initialize_schema,
)
from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    chats,
    document_recovery_runs,
    metadata,
    schema_migrations,
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


class DocumentRecoverySchemaV2Tests(
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
            / "schema-v2.db"
        )

        self.engine = build_sqlite_engine(
            self.database_path
        )

    def tearDown(self):
        self.engine.dispose()

        self.temporary_directory.cleanup()

    def create_version_one_schema(
        self,
    ) -> None:
        metadata.create_all(
            bind=self.engine,
            tables=[
                schema_migrations,
                *_SCHEMA_V1_APPLICATION_TABLES,
            ],
            checkfirst=True,
        )

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=1,
                    description=(
                        "Initial cross-database "
                        "chat persistence schema"
                    ),
                    applied_at=(
                        "2026-07-20T00:00:00+00:00"
                    ),
                )
            )

    def test_schema_version_and_safe_columns(
        self,
    ):
        self.assertEqual(
            SCHEMA_VERSION,
            2,
        )

        self.assertIn(
            document_recovery_runs.name,
            EXPECTED_TABLE_NAMES,
        )

        expected_columns = {
            "run_id",
            "status",
            "recovery_enabled",
            "started_at",
            "finished_at",
            "duration_ms",
            "total_examined",
            "candidate_count",
            "processing_recovered_count",
            "deleting_completed_count",
            "failure_count",
            "skipped_count",
            "recent_count",
            "invalid_timestamp_count",
            "deferred_count",
        }

        self.assertEqual(
            set(
                document_recovery_runs.c.keys()
            ),
            expected_columns,
        )

        forbidden_columns = {
            "error",
            "exception",
            "filename",
            "document_id",
            "file_path",
            "storage_key",
            "lock_id",
            "database_url",
        }

        self.assertFalse(
            expected_columns
            & forbidden_columns
        )

    def test_fresh_database_records_only_version_two(
        self,
    ):
        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            2,
        )

        self.assertEqual(
            get_schema_version(
                self.engine
            ),
            2,
        )

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            versions,
            [2],
        )

        self.assertIn(
            document_recovery_runs.name,
            inspect(
                self.engine
            ).get_table_names(),
        )

    def test_version_one_database_migrates_without_data_loss(
        self,
    ):
        self.create_version_one_schema()

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE preserved_v1_data (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            connection.exec_driver_sql(
                """
                INSERT INTO preserved_v1_data (
                    id,
                    value
                )
                VALUES (1, 'keep-me')
                """
            )

        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            2,
        )

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

            preserved_value = (
                connection.exec_driver_sql(
                    """
                    SELECT value
                    FROM preserved_v1_data
                    WHERE id = 1
                    """
                ).scalar_one()
            )

        self.assertEqual(
            versions,
            [
                1,
                2,
            ],
        )

        self.assertEqual(
            preserved_value,
            "keep-me",
        )

    def test_version_one_migration_is_idempotent(
        self,
    ):
        self.create_version_one_schema()

        initialize_schema(
            self.engine
        )

        initialize_schema(
            self.engine
        )

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            versions,
            [
                1,
                2,
            ],
        )

    def test_partial_version_one_schema_is_rejected(
        self,
    ):
        metadata.create_all(
            bind=self.engine,
            tables=[
                schema_migrations,
                chats,
            ],
            checkfirst=True,
        )

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=1,
                    description=(
                        "Invalid partial schema"
                    ),
                    applied_at=(
                        "2026-07-20T00:00:00+00:00"
                    ),
                )
            )

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(
                self.engine
            )

    def test_data_migration_includes_recovery_history(
        self,
    ):
        self.assertIn(
            document_recovery_runs,
            data_migration._APPLICATION_TABLES,
        )

        self.assertIn(
            document_recovery_runs,
            data_migration._INSERT_ORDER,
        )

        self.assertNotIn(
            document_recovery_runs,
            data_migration._SEQUENCE_TABLES,
        )

    def test_legacy_source_without_history_table_migrates(
        self,
    ):
        source_path = (
            Path(
                self.temporary_directory.name
            )
            / "legacy-source.db"
        )

        target_path = (
            Path(
                self.temporary_directory.name
            )
            / "legacy-target.db"
        )

        source_engine = build_sqlite_engine(
            source_path
        )

        target_engine = build_sqlite_engine(
            target_path
        )

        try:
            metadata.create_all(
                bind=source_engine,
                tables=[
                    schema_migrations,
                    *_SCHEMA_V1_APPLICATION_TABLES,
                ],
                checkfirst=True,
            )

            with source_engine.begin() as connection:
                connection.execute(
                    insert(
                        schema_migrations
                    ).values(
                        version=1,
                        description=(
                            "Initial cross-database "
                            "chat persistence schema"
                        ),
                        applied_at=(
                            "2026-07-20T00:00:00+00:00"
                        ),
                    )
                )

            source_engine.dispose()

            audit_report = (
                data_migration
                .audit_sqlite_database(
                    source_path
                )
            )

            self.assertEqual(
                audit_report.row_counts[
                    document_recovery_runs.name
                ],
                0,
            )

            migration_report = (
                data_migration
                .migrate_sqlite_database(
                    source_path,
                    target_engine,
                )
            )

            self.assertEqual(
                migration_report.row_counts[
                    document_recovery_runs.name
                ],
                0,
            )

            with target_engine.connect() as connection:
                stored_history_rows = (
                    connection.execute(
                        select(
                            document_recovery_runs
                            .c.run_id
                        )
                    ).scalars().all()
                )

            self.assertEqual(
                stored_history_rows,
                [],
            )
        finally:
            source_engine.dispose()
            target_engine.dispose()

    def test_history_table_accepts_only_safe_metrics(
        self,
    ):
        initialize_schema(
            self.engine
        )

        safe_values = {
            "run_id": "run-safe-1",
            "status": "completed",
            "recovery_enabled": 1,
            "started_at": (
                "2026-07-21T10:00:00+00:00"
            ),
            "finished_at": (
                "2026-07-21T10:00:01+00:00"
            ),
            "duration_ms": 1000,
            "total_examined": 3,
            "candidate_count": 2,
            "processing_recovered_count": 1,
            "deleting_completed_count": 1,
            "failure_count": 0,
            "skipped_count": 0,
            "recent_count": 1,
            "invalid_timestamp_count": 0,
            "deferred_count": 0,
        }

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    document_recovery_runs
                ).values(
                    **safe_values
                )
            )

        with self.engine.connect() as connection:
            stored_status = connection.execute(
                select(
                    document_recovery_runs.c.status
                ).where(
                    document_recovery_runs.c.run_id
                    == "run-safe-1"
                )
            ).scalar_one()

        self.assertEqual(
            stored_status,
            "completed",
        )

        invalid_values = dict(
            safe_values
        )

        invalid_values["run_id"] = (
            "run-invalid-1"
        )

        invalid_values["duration_ms"] = -1

        with self.assertRaises(
            IntegrityError
        ):
            with self.engine.begin() as connection:
                connection.execute(
                    insert(
                        document_recovery_runs
                    ).values(
                        **invalid_values
                    )
                )


if __name__ == "__main__":
    unittest.main()
