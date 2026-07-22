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
    SchemaVersionError,
    _SCHEMA_V2_APPLICATION_TABLES,
    _SCHEMA_V3_APPLICATION_TABLES,
    _validate_recorded_version,
    get_schema_version,
    initialize_schema,
    validate_existing_schema,
)
from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    metadata,
    schema_migrations,
    system_incident_alert_outbox,
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
            "2026-07-22T10:00:00+00:00"
        ),
        "last_seen_at": (
            "2026-07-22T10:00:01+00:00"
        ),
        "resolved_at": None,
        "occurrence_count": 1,
    }


def safe_outbox_values(
    delivery_id: str = "delivery-safe-1",
    *,
    state: str = "pending",
) -> dict:
    claimed_at = None
    claim_token = None
    completed_at = None
    attempt_count = 0

    if state == "processing":
        claimed_at = (
            "2026-07-22T10:01:00+00:00"
        )
        claim_token = "claim-processing-1"
        attempt_count = 1
    elif state in {
        "completed",
        "failed",
    }:
        claimed_at = (
            "2026-07-22T10:01:00+00:00"
        )
        claim_token = "claim-terminal-1"
        completed_at = (
            "2026-07-22T10:02:00+00:00"
        )
        attempt_count = (
            1
            if state == "completed"
            else 5
        )

    return {
        "delivery_id": delivery_id,
        "payload_json": (
            '{"event":"incident_transitions",'
            '"transitions":[]}'
        ),
        "state": state,
        "attempt_count": attempt_count,
        "max_attempts": 5,
        "next_attempt_at": (
            "2026-07-22T10:00:00+00:00"
        ),
        "claimed_at": claimed_at,
        "claim_token": claim_token,
        "created_at": (
            "2026-07-22T10:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-22T10:00:00+00:00"
        ),
        "completed_at": completed_at,
    }


class SystemIncidentSchemaV4Tests(
    unittest.TestCase
):
    def setUp(
        self,
    ):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.database_path = (
            Path(
                self.temporary_directory.name
            )
            / "schema-v4.db"
        )

        self.engine = build_sqlite_engine(
            self.database_path
        )

    def tearDown(
        self,
    ):
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
                        "2026-07-22T00:00:00+00:00"
                    ),
                )
            )

    def create_version_three_schema(
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
                *_SCHEMA_V3_APPLICATION_TABLES,
            ],
            checkfirst=True,
        )

        with resolved_engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=3,
                    description=(
                        "Add durable system "
                        "incident history"
                    ),
                    applied_at=(
                        "2026-07-22T00:00:00+00:00"
                    ),
                )
            )

    def test_schema_version_and_safe_outbox_columns(
        self,
    ):
        self.assertEqual(
            SCHEMA_VERSION,
            4,
        )

        self.assertIn(
            system_incident_alert_outbox.name,
            EXPECTED_TABLE_NAMES,
        )

        expected_columns = {
            "delivery_id",
            "payload_json",
            "state",
            "attempt_count",
            "max_attempts",
            "next_attempt_at",
            "claimed_at",
            "claim_token",
            "created_at",
            "updated_at",
            "completed_at",
        }

        self.assertEqual(
            set(
                system_incident_alert_outbox.c.keys()
            ),
            expected_columns,
        )

        forbidden_columns = {
            "webhook_url",
            "authorization",
            "credential",
            "password",
            "secret",
            "token_sha256",
            "database_url",
            "traceback",
            "exception",
        }

        self.assertFalse(
            expected_columns
            & forbidden_columns
        )

    def test_fresh_database_records_only_version_four(
        self,
    ):
        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            4,
        )

        self.assertEqual(
            get_schema_version(
                self.engine
            ),
            4,
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
            [4],
        )

        table_names = set(
            inspect(
                self.engine
            ).get_table_names()
        )

        self.assertIn(
            system_incidents.name,
            table_names,
        )

        self.assertIn(
            system_incident_alert_outbox.name,
            table_names,
        )

    def test_valid_recorded_histories_are_accepted(
        self,
    ):
        valid_histories = (
            (),
            (1,),
            (2,),
            (3,),
            (4,),
            (1, 2),
            (2, 3),
            (3, 4),
            (1, 2, 3),
            (2, 3, 4),
            (1, 2, 3, 4),
        )

        for history in valid_histories:
            with self.subTest(
                history=history
            ):
                _validate_recorded_version(
                    history
                )

        for history in (
            (1, 3),
            (2, 4),
            (1, 2, 4),
            (4, 3),
            (3, 3, 4),
        ):
            with self.subTest(
                invalid_history=history
            ):
                with self.assertRaises(
                    SchemaVersionError
                ):
                    _validate_recorded_version(
                        history
                    )

    def test_unrecorded_version_four_schema_is_inferred(
        self,
    ):
        metadata.create_all(
            bind=self.engine,
            checkfirst=True,
        )

        validate_existing_schema(
            self.engine
        )

        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            4,
        )

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            versions,
            [4],
        )

    def test_version_two_database_records_versions_three_and_four(
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
            4,
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
                4,
            ],
        )

        self.assertEqual(
            preserved_value,
            "keep-v2-data",
        )

    def test_version_three_database_preserves_incident_rows(
        self,
    ):
        self.create_version_three_schema()

        values = safe_incident_values(
            "incident-preserved-v3"
        )

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    system_incidents
                ).values(
                    **values
                )
            )

        version = initialize_schema(
            self.engine
        )

        self.assertEqual(
            version,
            4,
        )

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

            stored_id = connection.execute(
                select(
                    system_incidents.c.incident_id
                )
            ).scalar_one()

        self.assertEqual(
            versions,
            [
                3,
                4,
            ],
        )

        self.assertEqual(
            stored_id,
            "incident-preserved-v3",
        )

    def test_version_three_migration_is_idempotent(
        self,
    ):
        self.create_version_three_schema()

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
                3,
                4,
            ],
        )

    def test_partial_version_three_schema_is_rejected(
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
                    version=3,
                    description=(
                        "Invalid partial v3 schema"
                    ),
                    applied_at=(
                        "2026-07-22T00:00:00+00:00"
                    ),
                )
            )

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(
                self.engine
            )

    def test_outbox_enforces_safe_delivery_lifecycle(
        self,
    ):
        initialize_schema(
            self.engine
        )

        valid_rows = [
            safe_outbox_values(
                "delivery-pending",
                state="pending",
            ),
            safe_outbox_values(
                "delivery-processing",
                state="processing",
            ),
            safe_outbox_values(
                "delivery-completed",
                state="completed",
            ),
            safe_outbox_values(
                "delivery-failed",
                state="failed",
            ),
        ]

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    system_incident_alert_outbox
                ),
                valid_rows,
            )

        with self.engine.connect() as connection:
            stored_states = connection.execute(
                select(
                    system_incident_alert_outbox.c.state
                ).order_by(
                    system_incident_alert_outbox.c.delivery_id
                )
            ).scalars().all()

        self.assertEqual(
            stored_states,
            [
                "completed",
                "failed",
                "pending",
                "processing",
            ],
        )

        invalid_rows = []

        invalid_state = safe_outbox_values(
            "delivery-invalid-state"
        )
        invalid_state["state"] = "unknown"
        invalid_rows.append(
            invalid_state
        )

        invalid_attempts = safe_outbox_values(
            "delivery-invalid-attempts"
        )
        invalid_attempts["attempt_count"] = 6
        invalid_rows.append(
            invalid_attempts
        )

        invalid_payload = safe_outbox_values(
            "delivery-invalid-payload"
        )
        invalid_payload["payload_json"] = "x"
        invalid_rows.append(
            invalid_payload
        )

        invalid_processing = safe_outbox_values(
            "delivery-invalid-processing",
            state="processing",
        )
        invalid_processing["claim_token"] = None
        invalid_rows.append(
            invalid_processing
        )

        invalid_completed = safe_outbox_values(
            "delivery-invalid-completed",
            state="completed",
        )
        invalid_completed["completed_at"] = None
        invalid_rows.append(
            invalid_completed
        )

        for invalid_row in invalid_rows:
            with self.subTest(
                delivery_id=(
                    invalid_row["delivery_id"]
                )
            ):
                with self.assertRaises(
                    IntegrityError
                ):
                    with self.engine.begin() as connection:
                        connection.execute(
                            insert(
                                system_incident_alert_outbox
                            ).values(
                                **invalid_row
                            )
                        )

    def test_outbox_indexes_support_due_scans_and_claims(
        self,
    ):
        initialize_schema(
            self.engine
        )

        index_names = {
            index["name"]
            for index in inspect(
                self.engine
            ).get_indexes(
                system_incident_alert_outbox.name
            )
        }

        self.assertIn(
            "ix_system_incident_alert_outbox_due",
            index_names,
        )

        self.assertIn(
            "ix_system_incident_alert_outbox_claim",
            index_names,
        )

    def test_data_migration_includes_optional_outbox_table(
        self,
    ):
        self.assertIn(
            system_incident_alert_outbox,
            data_migration._APPLICATION_TABLES,
        )
        self.assertIn(
            system_incident_alert_outbox,
            data_migration._INSERT_ORDER,
        )
        self.assertIn(
            system_incident_alert_outbox.name,
            data_migration._OPTIONAL_SOURCE_TABLE_NAMES,
        )
        self.assertNotIn(
            system_incident_alert_outbox,
            data_migration._SEQUENCE_TABLES,
        )

    def test_version_three_source_without_outbox_migrates(
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
            / "target-v4.db"
        )

        source_engine = build_sqlite_engine(
            source_path
        )
        target_engine = build_sqlite_engine(
            target_path
        )

        try:
            self.create_version_three_schema(
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
                    system_incident_alert_outbox.name
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
                    system_incident_alert_outbox.name
                ],
                0,
            )

            self.assertEqual(
                get_schema_version(
                    target_engine
                ),
                4,
            )
        finally:
            source_engine.dispose()
            target_engine.dispose()

    def test_version_four_outbox_rows_migrate(
        self,
    ):
        source_path = (
            Path(
                self.temporary_directory.name
            )
            / "source-v4.db"
        )
        target_path = (
            Path(
                self.temporary_directory.name
            )
            / "target-copy-v4.db"
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

            values = safe_outbox_values(
                "delivery-migrate-1"
            )

            with source_engine.begin() as connection:
                connection.execute(
                    insert(
                        system_incident_alert_outbox
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
                    system_incident_alert_outbox.name
                ],
                1,
            )

            with target_engine.connect() as connection:
                stored = connection.execute(
                    select(
                        system_incident_alert_outbox.c.delivery_id,
                        system_incident_alert_outbox.c.payload_json,
                        system_incident_alert_outbox.c.state,
                    )
                ).one()

            self.assertEqual(
                tuple(
                    stored
                ),
                (
                    "delivery-migrate-1",
                    values["payload_json"],
                    "pending",
                ),
            )
        finally:
            source_engine.dispose()
            target_engine.dispose()


if __name__ == "__main__":
    unittest.main()
