import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config.database import load_database_settings
from app.database.engine import build_database_engine
from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    branch_merge_message_mappings,
    branch_merge_operations,
    chats,
    create_schema,
    documents,
    folders,
    messages,
    metadata,
)


class DatabaseSchemaTests(unittest.TestCase):
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
        create_schema(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def test_expected_tables_are_created(self):
        table_names = set(
            inspect(self.engine).get_table_names()
        )

        self.assertEqual(
            table_names,
            EXPECTED_TABLE_NAMES,
        )

    def test_repeated_initialization_is_idempotent(self):
        create_schema(self.engine)
        create_schema(self.engine)

        table_names = set(
            inspect(self.engine).get_table_names()
        )

        self.assertEqual(
            table_names,
            EXPECTED_TABLE_NAMES,
        )

    def test_current_schema_version_is_six(self):
        self.assertEqual(
            SCHEMA_VERSION,
            6,
        )

    def test_messages_include_nullable_agent_id(self):
        columns = {
            column["name"]: column
            for column in inspect(
                self.engine
            ).get_columns(
                messages.name
            )
        }

        self.assertIn(
            "agent_id",
            columns,
        )
        self.assertTrue(
            columns["agent_id"]["nullable"]
        )

    def test_sqlite_generated_numeric_ids(self):
        with self.engine.begin() as connection:
            result = connection.execute(
                chats.insert().values(
                    title="Generated ID",
                    created_at="2026-07-19T12:00:00",
                )
            )

        self.assertEqual(
            result.inserted_primary_key,
            (1,),
        )

    def test_folder_names_are_case_insensitively_unique(self):
        with self.engine.begin() as connection:
            connection.execute(
                folders.insert().values(
                    name="Projects",
                    created_at="2026-07-19T12:00:00",
                )
            )

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    folders.insert().values(
                        name="projects",
                        created_at=(
                            "2026-07-19T12:01:00"
                        ),
                    )
                )

    def test_document_names_are_unique_per_chat_ignoring_case(
        self,
    ):
        common_values = {
            "chat_id": 1,
            "file_path": "storage/pdfs/file.pdf",
            "file_hash": "a" * 64,
            "uploaded_at": "2026-07-19T12:00:00",
            "updated_at": "2026-07-19T12:00:00",
        }

        with self.engine.begin() as connection:
            connection.execute(
                documents.insert().values(
                    document_id="doc-1",
                    filename="Report.PDF",
                    **common_values,
                )
            )

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    documents.insert().values(
                        document_id="doc-2",
                        filename="report.pdf",
                        **common_values,
                    )
                )

    def test_branch_merge_status_constraint(self):
        valid_values = {
            "idempotency_key": "key-1",
            "request_fingerprint": "b" * 64,
            "preview_token": "c" * 64,
            "branch_chat_id": 2,
            "parent_chat_id": 1,
            "branched_from_message_id": 10,
            "branch_message_id": 11,
            "expected_parent_last_message_id": 10,
            "expected_branch_last_message_id": 11,
            "created_at": "2026-07-19T12:00:00",
        }

        with self.engine.begin() as connection:
            connection.execute(
                branch_merge_operations.insert().values(
                    status="pending",
                    **valid_values,
                )
            )

        invalid_values = dict(valid_values)
        invalid_values["idempotency_key"] = "key-2"

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    branch_merge_operations.insert().values(
                        status="failed",
                        **invalid_values,
                    )
                )

    def test_audit_tables_intentionally_have_no_foreign_keys(
        self,
    ):
        inspector = inspect(self.engine)

        self.assertEqual(
            inspector.get_foreign_keys(
                branch_merge_operations.name
            ),
            [],
        )
        self.assertEqual(
            inspector.get_foreign_keys(
                branch_merge_message_mappings.name
            ),
            [],
        )

    def test_postgresql_ddl_has_no_sqlite_only_syntax(self):
        dialect = postgresql.dialect()

        statements = []

        for table in metadata.sorted_tables:
            statements.append(
                str(
                    CreateTable(table).compile(
                        dialect=dialect
                    )
                )
            )

            for index in table.indexes:
                statements.append(
                    str(
                        CreateIndex(index).compile(
                            dialect=dialect
                        )
                    )
                )

        ddl = "\n".join(statements).upper()

        self.assertIn("SERIAL", ddl)
        self.assertNotIn("AUTOINCREMENT", ddl)
        self.assertNotIn("PRAGMA", ddl)
        self.assertNotIn("COLLATE NOCASE", ddl)


if __name__ == "__main__":
    unittest.main()
