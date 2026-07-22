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
from app.database import data_migration
from app.database.engine import (
    build_database_engine,
)
from app.database.migrations import (
    SchemaCompatibilityError,
    _SCHEMA_V2_APPLICATION_TABLES,
    get_schema_version,
    initialize_schema,
)
from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    metadata,
    schema_migrations,
    system_incidents,
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


def safe_incident_values(
    incident_id: str = "incident-safe-1",
) -> dict:
    return {
        "incident_id": incident_id,
        "incident_key": (
            "system_health:database"
        ),
        "component": "database",
        "severity": "critical",
        "source_status": "unavailable",
        "detail": "database_unreachable",
        "critical": 1,
        "state": "open",
        "fingerprint": "a" * 64,
        "opened_at": (
            "2026-07-21T10:00:00+00:00"
        ),
        "last_seen_at": (
            "2026-07-21T10:00:01+00:00"
        ),
        "resolved_at": None,
        "occurrence_count": 1,
    }


class SystemIncidentSchemaV3Tests(
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
            / "schema-v3.db"
        )

        self.engine = build_sqlite_engine(
            self.database_path
        )

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def create_version_two_schema(
        self,
        engine=None,
    ) -> None:
        resolved_engine = (
            self.engine
            if engine is None
            else engine
        )

        metadata.create_all(
            bind=resolved_engine,
            tables=[
                schema_migrations,
                *_SCHEMA_V2_APPLICATION_TABLES,
            ],
            checkfirst=True,
        )

        with resolved_engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=2,
                    description=(
                        "Add document recovery "
                        "run history"
                    ),
                    applied_at=(
                        "2026-07-21T00:00:00+00:00"
                    ),
                )
            )

    def test_schema_version_and_safe_columns(
        self,
    ):
        self.assertEqual(
            SCHEMA_VERSION,
            3,
        )

        self.assertIn(
            system_incidents.name,
            EXPECTED_TABLE_NAMES,
        )

        expected_columns = {
            "incident_id",
            "incident_key",
            "component",
            "severity",
            "source_status",
            "detail",
            "critical",
            "state",
            "fingerprint",
            "opened_at",
            "last_seen_at",
            "resolved_at",
            "occurrence_count",
        }

        self.assertEqual(
            set(
                system_incidents.c.keys()
            ),
            expected_columns,
        )

        forbidden_columns = {
            "error",
            "exception",
            "traceback",
            "password",
            "database_url",
            "storage_key",
            "document_id",
            "filename",
            "file_path",
            "access_key",
            "secret_key",
        }

        self.assertFalse(
            expected_columns
            & forbidden_columns
        )

    def test_fresh_database_records_only_version_three(
        self,
    ):
        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            3,
        )

        self.assertEqual(
            get_schema_version(
                self.engine
            ),
            3,
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
            [3],
        )

        self.assertIn(
            system_incidents.name,
            inspect(
                self.engine
            ).get_table_names(),
        )

    def test_version_two_database_migrates_without_data_loss(
        self,
    ):
        self.create_version_two_schema()

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE preserved_v2_data (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            connection.exec_driver_sql(
                """
                INSERT INTO preserved_v2_data (
                    id,
                    value
                )
                VALUES (1, 'keep-v2-data')
                """
            )

        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            3,
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
                    FROM preserved_v2_data
                    WHERE id = 1
                    """
                ).scalar_one()
            )

        self.assertEqual(
            versions,
            [
                2,
                3,
            ],
        )

        self.assertEqual(
            preserved_value,
            "keep-v2-data",
        )

    def test_version_two_migration_is_idempotent(
        self,
    ):
        self.create_version_two_schema()

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
                2,
                3,
            ],
        )

    def test_partial_version_two_schema_is_rejected(
        self,
    ):
        metadata.create_all(
            bind=self.engine,
            tables=[
                schema_migrations,
            ],
            checkfirst=True,
        )

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=2,
                    description=(
                        "Invalid partial v2 schema"
                    ),
                    applied_at=(
                        "2026-07-21T00:00:00+00:00"
                    ),
                )
            )

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(
                self.engine
            )

    def test_incident_table_enforces_safe_lifecycle_values(
        self,
    ):
        initialize_schema(
            self.engine
        )

        values = safe_incident_values()

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    system_incidents
                ).values(
                    **values
                )
            )

        with self.engine.connect() as connection:
            stored_state = connection.execute(
                select(
                    system_incidents.c.state
                ).where(
                    system_incidents.c.incident_id
                    == values["incident_id"]
                )
            ).scalar_one()

        self.assertEqual(
            stored_state,
            "open",
        )

        invalid_count = dict(
            values
        )

        invalid_count["incident_id"] = (
            "incident-invalid-count"
        )

        invalid_count["occurrence_count"] = 0

        with self.assertRaises(
            IntegrityError
        ):
            with self.engine.begin() as connection:
                connection.execute(
                    insert(
                        system_incidents
                    ).values(
                        **invalid_count
                    )
                )

        invalid_resolution = dict(
            values
        )

        invalid_resolution["incident_id"] = (
            "incident-invalid-resolution"
        )

        invalid_resolution["state"] = (
            "resolved"
        )

        with self.assertRaises(
            IntegrityError
        ):
            with self.engine.begin() as connection:
                connection.execute(
                    insert(
                        system_incidents
                    ).values(
                        **invalid_resolution
                    )
                )

    def test_data_migration_includes_incident_table(
        self,
    ):
        self.assertIn(
            system_incidents,
            data_migration._APPLICATION_TABLES,
        )

        self.assertIn(
            system_incidents,
            data_migration._INSERT_ORDER,
        )

        self.assertIn(
            system_incidents.name,
            (
                data_migration
                ._OPTIONAL_SOURCE_TABLE_NAMES
            ),
        )

        self.assertNotIn(
            system_incidents,
            data_migration._SEQUENCE_TABLES,
        )

    def test_version_two_source_without_incidents_migrates(
        self,
    ):
        source_path = (
            Path(
                self.temporary_directory.name
            )
            / "source-v2.db"
        )

        target_path = (
            Path(
                self.temporary_directory.name
            )
            / "target-v3.db"
        )

        source_engine = build_sqlite_engine(
            source_path
        )

        target_engine = build_sqlite_engine(
            target_path
        )

        try:
            self.create_version_two_schema(
                source_engine
            )

            audit_report = (
                data_migration
                .audit_sqlite_database(
                    source_path
                )
            )

            self.assertEqual(
                audit_report.row_counts[
                    system_incidents.name
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
                    system_incidents.name
                ],
                0,
            )

            self.assertEqual(
                get_schema_version(
                    target_engine
                ),
                3,
            )

            with target_engine.connect() as connection:
                incident_rows = connection.execute(
                    select(
                        system_incidents.c.incident_id
                    )
                ).scalars().all()

            self.assertEqual(
                incident_rows,
                [],
            )
        finally:
            source_engine.dispose()
            target_engine.dispose()

    def test_version_three_incident_rows_migrate(
        self,
    ):
        source_path = (
            Path(
                self.temporary_directory.name
            )
            / "source-v3.db"
        )

        target_path = (
            Path(
                self.temporary_directory.name
            )
            / "target-copy-v3.db"
        )

        source_engine = build_sqlite_engine(
            source_path
        )

        target_engine = build_sqlite_engine(
            target_path
        )

        try:
            initialize_schema(
                source_engine
            )

            values = safe_incident_values(
                "incident-migrate-1"
            )

            with source_engine.begin() as connection:
                connection.execute(
                    insert(
                        system_incidents
                    ).values(
                        **values
                    )
                )

            report = (
                data_migration
                .migrate_sqlite_database(
                    source_path,
                    target_engine,
                )
            )

            self.assertEqual(
                report.row_counts[
                    system_incidents.name
                ],
                1,
            )

            with target_engine.connect() as connection:
                stored_id = connection.execute(
                    select(
                        system_incidents.c.incident_id
                    )
                ).scalar_one()

            self.assertEqual(
                stored_id,
                "incident-migrate-1",
            )
        finally:
            source_engine.dispose()
            target_engine.dispose()


if __name__ == "__main__":
    unittest.main()
