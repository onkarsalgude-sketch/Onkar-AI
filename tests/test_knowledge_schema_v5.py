import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, insert, select
from sqlalchemy.exc import IntegrityError

from app.config.database import load_database_settings
from app.database import data_migration
from app.database.engine import build_database_engine
from app.database.migrations import (
    SchemaCompatibilityError,
    SchemaVersionError,
    _SCHEMA_V4_APPLICATION_TABLES,
    _validate_recorded_version,
    get_schema_version,
    initialize_schema,
    validate_existing_schema,
)
from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    knowledge_documents,
    metadata,
    schema_migrations,
)


class KnowledgeSchemaV5Tests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "knowledge-v5.db"
        settings = load_database_settings({}, default_sqlite_path=self.database_path)
        self.engine = build_database_engine(settings)

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def create_version_four_schema(self, engine=None):
        target_engine = engine or self.engine
        metadata.create_all(
            bind=target_engine,
            tables=[schema_migrations, *_SCHEMA_V4_APPLICATION_TABLES],
            checkfirst=True,
        )
        with target_engine.begin() as connection:
            connection.execute(
                insert(schema_migrations).values(
                    version=4,
                    description="Durable incident alert outbox",
                    applied_at="2026-07-22T00:00:00+00:00",
                )
            )

    def test_schema_version_and_safe_columns(self):
        self.assertEqual(SCHEMA_VERSION, 5)
        self.assertIn(knowledge_documents.name, EXPECTED_TABLE_NAMES)
        expected_columns = {
            "knowledge_id", "title", "filename", "object_key", "file_hash",
            "file_size", "page_count", "chunk_count", "status", "is_enabled",
            "created_at", "updated_at",
        }
        self.assertEqual(set(knowledge_documents.c.keys()), expected_columns)
        forbidden_columns = {
            "content", "embedding", "credential", "password", "secret",
            "database_url", "chat_id",
        }
        self.assertFalse(expected_columns & forbidden_columns)

    def test_constraints_and_indexes_are_enforced(self):
        initialize_schema(self.engine)
        common = {
            "title": "Operating Guide",
            "filename": "operating-guide.pdf",
            "object_key": "knowledge/operating-guide.pdf",
            "file_hash": "a" * 64,
            "file_size": 1024,
            "page_count": 4,
            "chunk_count": 12,
            "status": "ready",
            "is_enabled": 1,
            "created_at": "2026-07-22T00:00:00+00:00",
            "updated_at": "2026-07-22T00:00:00+00:00",
        }
        with self.engine.begin() as connection:
            connection.execute(
                insert(knowledge_documents).values(knowledge_id="knowledge-1", **common)
            )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                duplicate = dict(common)
                duplicate["filename"] = "duplicate.pdf"
                connection.execute(
                    insert(knowledge_documents).values(
                        knowledge_id="knowledge-2",
                        **duplicate,
                    )
                )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                invalid = dict(common)
                invalid["file_hash"] = "b" * 64
                invalid["status"] = "unsafe"
                connection.execute(
                    insert(knowledge_documents).values(
                        knowledge_id="knowledge-3",
                        **invalid,
                    )
                )
        index_names = {
            item["name"]
            for item in inspect(self.engine).get_indexes(knowledge_documents.name)
        }
        self.assertTrue(
            {
                "ux_knowledge_documents_file_hash",
                "ix_knowledge_documents_status_updated",
                "ix_knowledge_documents_enabled_updated",
            }.issubset(index_names)
        )

    def test_fresh_database_records_only_version_five(self):
        version = initialize_schema(self.engine)
        self.assertEqual(version, 5)
        self.assertEqual(get_schema_version(self.engine), 5)
        with self.engine.connect() as connection:
            versions = connection.execute(
                select(schema_migrations.c.version).order_by(schema_migrations.c.version)
            ).scalars().all()
        self.assertEqual(versions, [5])
        self.assertIn(knowledge_documents.name, inspect(self.engine).get_table_names())

    def test_valid_recorded_histories_are_accepted(self):
        valid_histories = (
            (), (1,), (2,), (3,), (4,), (5,),
            (1, 2), (2, 3), (3, 4), (4, 5),
            (1, 2, 3), (2, 3, 4), (3, 4, 5),
            (1, 2, 3, 4), (2, 3, 4, 5), (1, 2, 3, 4, 5),
        )
        for history in valid_histories:
            with self.subTest(history=history):
                _validate_recorded_version(history)
        for history in (
            (1, 3), (2, 4), (3, 5), (1, 2, 4),
            (2, 3, 5), (5, 4), (4, 4, 5), (6,),
        ):
            with self.subTest(invalid_history=history):
                with self.assertRaises(SchemaVersionError):
                    _validate_recorded_version(history)

    def test_unrecorded_version_five_schema_is_inferred(self):
        metadata.create_all(bind=self.engine, checkfirst=True)
        validate_existing_schema(self.engine)
        version = initialize_schema(self.engine)
        self.assertEqual(version, 5)
        with self.engine.connect() as connection:
            versions = connection.execute(select(schema_migrations.c.version)).scalars().all()
        self.assertEqual(versions, [5])

    def test_version_four_database_migrates_without_data_loss(self):
        self.create_version_four_schema()
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE preserved_v4_data (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO preserved_v4_data (id, value) VALUES (1, 'keep-v4-data')"
            )
        version = initialize_schema(self.engine)
        self.assertEqual(version, 5)
        with self.engine.connect() as connection:
            versions = connection.execute(
                select(schema_migrations.c.version).order_by(schema_migrations.c.version)
            ).scalars().all()
            preserved_value = connection.exec_driver_sql(
                "SELECT value FROM preserved_v4_data WHERE id = 1"
            ).scalar_one()
        self.assertEqual(versions, [4, 5])
        self.assertEqual(preserved_value, "keep-v4-data")
        self.assertIn(knowledge_documents.name, inspect(self.engine).get_table_names())

    def test_version_four_migration_is_idempotent(self):
        self.create_version_four_schema()
        initialize_schema(self.engine)
        initialize_schema(self.engine)
        with self.engine.connect() as connection:
            versions = connection.execute(
                select(schema_migrations.c.version).order_by(schema_migrations.c.version)
            ).scalars().all()
        self.assertEqual(versions, [4, 5])

    def test_partial_version_four_schema_is_rejected(self):
        metadata.create_all(bind=self.engine, tables=[schema_migrations], checkfirst=True)
        with self.engine.begin() as connection:
            connection.execute(
                insert(schema_migrations).values(
                    version=4,
                    description="Invalid partial v4 schema",
                    applied_at="2026-07-22T00:00:00+00:00",
                )
            )
        with self.assertRaises(SchemaCompatibilityError):
            initialize_schema(self.engine)

    def test_version_four_source_without_knowledge_migrates(self):
        source_path = Path(self.temporary_directory.name) / "source-v4.db"
        target_path = Path(self.temporary_directory.name) / "target-v5.db"
        source_engine = build_database_engine(
            load_database_settings({}, default_sqlite_path=source_path)
        )
        target_engine = build_database_engine(
            load_database_settings({}, default_sqlite_path=target_path)
        )
        try:
            self.create_version_four_schema(source_engine)
            source_engine.dispose()
            audit_report = data_migration.audit_sqlite_database(source_path)
            self.assertEqual(audit_report.row_counts[knowledge_documents.name], 0)
            migration_report = data_migration.migrate_sqlite_database(
                source_path,
                target_engine,
            )
            self.assertEqual(
                migration_report.row_counts[knowledge_documents.name],
                0,
            )
            self.assertEqual(get_schema_version(target_engine), 5)
        finally:
            source_engine.dispose()
            target_engine.dispose()


if __name__ == "__main__":
    unittest.main()
