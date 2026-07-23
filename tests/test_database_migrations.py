import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, insert, inspect, select

from app.config.database import load_database_settings
from app.database.engine import build_database_engine
from app.database.migrations import (
    SchemaCompatibilityError,
    SchemaVersionError,
    get_schema_version,
    initialize_schema,
    validate_existing_schema,
)
from app.database.schema import (
    SCHEMA_VERSION,
    chats,
    create_schema,
    messages,
    schema_migrations,
)
from app.services import history_service


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = (
            Path(self.temporary_directory.name)
            / "chat_history.db"
        )

        settings = load_database_settings(
            {},
            default_sqlite_path=self.database_path,
        )

        self.engine = build_database_engine(settings)

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def _drop_agent_id_column(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE messages "
                "DROP COLUMN agent_id"
            )

    def _stamp_versions(self, versions):
        with self.engine.begin() as connection:
            for version in versions:
                connection.execute(
                    insert(
                        schema_migrations
                    ).values(
                        version=version,
                        description=(
                            f"Schema version {version}"
                        ),
                        applied_at=(
                            "2026-07-19T12:00:00+00:00"
                        ),
                    )
                )

    def test_fresh_schema_records_version(self):
        self.assertEqual(
            get_schema_version(self.engine),
            0,
        )

        version = initialize_schema(self.engine)

        self.assertEqual(
            version,
            SCHEMA_VERSION,
        )
        self.assertEqual(
            get_schema_version(self.engine),
            SCHEMA_VERSION,
        )

    def test_repeated_initialization_is_idempotent(self):
        initialize_schema(self.engine)
        initialize_schema(self.engine)
        initialize_schema(self.engine)

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            versions,
            [SCHEMA_VERSION],
        )

    def test_version_five_adds_agent_id_without_data_loss(
        self,
    ):
        create_schema(self.engine)
        self._drop_agent_id_column()
        self._stamp_versions((5,))

        with self.engine.begin() as connection:
            connection.execute(
                chats.insert().values(
                    title="Version Five Chat",
                    created_at=(
                        "2026-07-19T12:00:00"
                    ),
                )
            )
            connection.exec_driver_sql(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    model_id,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "assistant",
                    "Preserved response",
                    "2026-07-19T12:01:00",
                    "[]",
                    "model-a",
                    None,
                ),
            )

        version = initialize_schema(
            self.engine
        )

        columns = {
            column["name"]
            for column in inspect(
                self.engine
            ).get_columns(
                messages.name
            )
        }

        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    messages.c.content,
                    messages.c.agent_id,
                )
            ).one()

            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            version,
            6,
        )
        self.assertIn(
            "agent_id",
            columns,
        )
        self.assertEqual(
            row.content,
            "Preserved response",
        )
        self.assertIsNone(
            row.agent_id
        )
        self.assertEqual(
            versions,
            [5, 6],
        )

    def test_version_five_migration_is_idempotent(
        self,
    ):
        create_schema(self.engine)
        self._drop_agent_id_column()
        self._stamp_versions((5,))

        initialize_schema(self.engine)
        initialize_schema(self.engine)
        initialize_schema(self.engine)

        columns = [
            column["name"]
            for column in inspect(
                self.engine
            ).get_columns(
                messages.name
            )
        ]

        with self.engine.connect() as connection:
            versions = connection.execute(
                select(
                    schema_migrations.c.version
                ).order_by(
                    schema_migrations.c.version
                )
            ).scalars().all()

        self.assertEqual(
            columns.count("agent_id"),
            1,
        )
        self.assertEqual(
            versions,
            [5, 6],
        )

    def test_version_four_records_versions_five_and_six(
        self,
    ):
        create_schema(self.engine)
        self._drop_agent_id_column()
        self._stamp_versions(
            (1, 2, 3, 4)
        )

        initialize_schema(self.engine)

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
            [1, 2, 3, 4, 5, 6],
        )

    def test_stamped_version_six_missing_agent_id_is_rejected(
        self,
    ):
        create_schema(self.engine)
        self._drop_agent_id_column()
        self._stamp_versions((6,))

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(self.engine)

    def test_legacy_sqlite_schema_is_adopted_without_data_loss(
        self,
    ):
        original_db_path = history_service.DB_PATH
        history_service.DB_PATH = str(
            self.database_path
        )

        try:
            history_service.init_db()

            connection = sqlite3.connect(
                self.database_path
            )

            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO chats (
                        title,
                        created_at,
                        is_pinned,
                        folder_id,
                        parent_chat_id,
                        branched_from_message_id,
                        branch_message_id
                    )
                    VALUES (?, ?, 0, NULL, NULL, NULL, NULL)
                    """,
                    (
                        "Legacy Chat",
                        "2026-07-19T12:00:00",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            version = initialize_schema(
                self.engine
            )

            with self.engine.connect() as connection:
                chat_count = connection.execute(
                    select(
                        func.count()
                    ).select_from(chats)
                ).scalar_one()

                title = connection.execute(
                    select(chats.c.title)
                ).scalar_one()

            self.assertEqual(
                version,
                SCHEMA_VERSION,
            )
            self.assertEqual(chat_count, 1)
            self.assertEqual(
                title,
                "Legacy Chat",
            )

        finally:
            history_service.DB_PATH = (
                original_db_path
            )

    def test_partial_legacy_schema_is_rejected_without_stamp(
        self,
    ):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            connection.execute(
                """
                CREATE TABLE chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    folder_id INTEGER,
                    parent_chat_id INTEGER,
                    branched_from_message_id INTEGER,
                    branch_message_id INTEGER
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(self.engine)

        connection = sqlite3.connect(
            self.database_path
        )

        try:
            schema_table = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'schema_migrations'
                """
            ).fetchone()
        finally:
            connection.close()

        self.assertIsNone(schema_table)

    def test_version_table_without_app_tables_is_rejected(
        self,
    ):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    version,
                    description,
                    applied_at
                )
                VALUES (1, 'Invalid partial schema', 'now')
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            initialize_schema(self.engine)


    def test_missing_case_insensitive_unique_index_is_rejected(
        self,
    ):
        create_schema(self.engine)

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP INDEX uq_folders_name_ci"
            )

        with self.assertRaises(
            SchemaCompatibilityError
        ):
            validate_existing_schema(
                self.engine
            )


    def test_future_schema_version_is_rejected(self):
        create_schema(self.engine)

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=SCHEMA_VERSION + 1,
                    description="Future schema",
                    applied_at=(
                        "2026-07-19T12:00:00+00:00"
                    ),
                )
            )

        with self.assertRaises(
            SchemaVersionError
        ):
            initialize_schema(self.engine)

    def test_older_recorded_version_requires_explicit_migration(
        self,
    ):
        create_schema(self.engine)

        with self.engine.begin() as connection:
            connection.execute(
                insert(
                    schema_migrations
                ).values(
                    version=0,
                    description="Legacy version",
                    applied_at=(
                        "2026-07-19T12:00:00+00:00"
                    ),
                )
            )

        with self.assertRaises(
            SchemaVersionError
        ):
            initialize_schema(self.engine)


if __name__ == "__main__":
    unittest.main()
