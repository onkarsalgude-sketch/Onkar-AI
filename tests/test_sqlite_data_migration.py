import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config.database import (
    load_database_settings,
)
from app.database.data_migration import (
    DataMigrationError,
    audit_sqlite_database,
    migrate_sqlite_database,
)
from app.database.engine import (
    build_database_engine,
)
from app.services import history_service


class SQLiteDataMigrationTests(
    unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temporary_directory.name
        )

        self.source_path = (
            self.root
            / "source.db"
        )

        self.target_path = (
            self.root
            / "target.db"
        )

        original_path = (
            history_service.DB_PATH
        )

        history_service.DB_PATH = str(
            self.source_path
        )

        try:
            history_service._legacy_init_db()
        finally:
            history_service.DB_PATH = (
                original_path
            )

        self._insert_source_data()

        settings = load_database_settings(
            {
                "SQLITE_DB_PATH": str(
                    self.target_path
                ),
            }
        )

        self.target_engine = (
            build_database_engine(
                settings
            )
        )

    def tearDown(self):
        self.target_engine.dispose()
        self.temporary_directory.cleanup()

    def _insert_source_data(self):
        connection = sqlite3.connect(
            self.source_path
        )

        try:
            connection.execute(
                """
                INSERT INTO folders (
                    id,
                    name,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    5,
                    "Migration",
                    "2026-07-19T10:00:00",
                ),
            )

            connection.execute(
                """
                INSERT INTO chats (
                    id,
                    title,
                    created_at,
                    is_pinned,
                    folder_id,
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    10,
                    "Parent",
                    "2026-07-19T10:01:00",
                    1,
                    5,
                    None,
                    None,
                    None,
                ),
            )

            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    model_id,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    100,
                    10,
                    "user",
                    "Parent message",
                    "2026-07-19T10:02:00",
                    "[]",
                    None,
                    None,
                ),
            )

            connection.execute(
                """
                INSERT INTO chats (
                    id,
                    title,
                    created_at,
                    is_pinned,
                    folder_id,
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    11,
                    "Branch",
                    "2026-07-19T10:03:00",
                    0,
                    5,
                    10,
                    100,
                    101,
                ),
            )

            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    model_id,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    101,
                    11,
                    "assistant",
                    "Branch message",
                    "2026-07-19T10:04:00",
                    "[]",
                    "test-model",
                    None,
                ),
            )

            connection.commit()

        finally:
            connection.close()

    def test_audit_reports_source_counts(
        self,
    ):
        report = audit_sqlite_database(
            self.source_path
        )

        self.assertEqual(
            report.row_counts["folders"],
            1,
        )
        self.assertEqual(
            report.row_counts["chats"],
            2,
        )
        self.assertEqual(
            report.row_counts["messages"],
            2,
        )
        self.assertEqual(
            report.total_rows,
            5,
        )

    def test_migration_preserves_ids_and_relationships(
        self,
    ):
        report = migrate_sqlite_database(
            self.source_path,
            self.target_engine,
        )

        self.assertEqual(
            report.target_backend,
            "sqlite",
        )

        connection = sqlite3.connect(
            self.target_path
        )

        try:
            branch_row = connection.execute(
                """
                SELECT
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id
                FROM chats
                WHERE id = ?
                """,
                (11,),
            ).fetchone()

            message_rows = connection.execute(
                """
                SELECT id, chat_id
                FROM messages
                ORDER BY id
                """
            ).fetchall()

            schema_version = (
                connection.execute(
                    """
                    SELECT version
                    FROM schema_migrations
                    """
                ).fetchone()
            )

        finally:
            connection.close()

        self.assertEqual(
            branch_row,
            (10, 100, 101),
        )
        self.assertEqual(
            message_rows,
            [
                (100, 10),
                (101, 11),
            ],
        )
        self.assertEqual(
            schema_version,
            (6,),
        )

    def test_nonempty_target_is_rejected(
        self,
    ):
        migrate_sqlite_database(
            self.source_path,
            self.target_engine,
        )

        with self.assertRaises(
            DataMigrationError
        ):
            migrate_sqlite_database(
                self.source_path,
                self.target_engine,
            )


if __name__ == "__main__":
    unittest.main()
