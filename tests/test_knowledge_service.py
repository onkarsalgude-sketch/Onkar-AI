import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.config.database import load_database_settings
from app.database.engine import build_database_engine
from app.database.migrations import initialize_schema
from app.services import knowledge_service


class KnowledgeMetadataServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = (
            Path(self.temporary_directory.name)
            / "knowledge-service.db"
        )
        settings = load_database_settings(
            {},
            default_sqlite_path=self.database_path,
        )
        self.engine = build_database_engine(
            settings
        )
        initialize_schema(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def create_record(
        self,
        *,
        knowledge_id="knowledge-1",
        title="Operating Guide",
        filename="operating-guide.pdf",
        object_key="knowledge/operating-guide.pdf",
        file_hash="a" * 64,
        file_size=1024,
    ):
        return (
            knowledge_service
            .create_knowledge_document(
                title=title,
                filename=filename,
                object_key=object_key,
                file_hash=file_hash,
                file_size=file_size,
                knowledge_id=knowledge_id,
                db_path=str(
                    self.database_path
                ),
            )
        )

    def test_create_get_and_list_round_trip(self):
        created = self.create_record(
            filename="../Operating-Guide.PDF",
        )

        self.assertEqual(
            created["knowledge_id"],
            "knowledge-1",
        )
        self.assertEqual(
            created["filename"],
            "Operating-Guide.PDF",
        )
        self.assertEqual(
            created["status"],
            "processing",
        )
        self.assertTrue(
            created["is_enabled"]
        )
        self.assertEqual(
            created["page_count"],
            0,
        )
        self.assertEqual(
            created["chunk_count"],
            0,
        )

        stored = (
            knowledge_service
            .get_knowledge_document(
                "knowledge-1",
                db_path=str(
                    self.database_path
                ),
            )
        )
        listed = (
            knowledge_service
            .list_knowledge_documents(
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertEqual(stored, created)
        self.assertEqual(listed, [created])

    def test_missing_record_returns_none(self):
        result = (
            knowledge_service
            .get_knowledge_document(
                "missing",
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertIsNone(result)

    def test_duplicate_hash_is_safe_and_rolls_back(self):
        self.create_record()

        with self.assertRaises(
            knowledge_service.KnowledgeMetadataError
        ) as captured:
            self.create_record(
                knowledge_id="knowledge-2",
                filename="duplicate.pdf",
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge metadata creation failed.",
        )
        self.assertNotIn(
            "UNIQUE",
            str(captured.exception),
        )
        self.assertNotIn(
            "knowledge/operating-guide.pdf",
            str(captured.exception),
        )

        second = self.create_record(
            knowledge_id="knowledge-3",
            filename="second.pdf",
            object_key="knowledge/second.pdf",
            file_hash="b" * 64,
        )

        self.assertEqual(
            second["knowledge_id"],
            "knowledge-3",
        )
        self.assertEqual(
            len(
                knowledge_service
                .list_knowledge_documents(
                    db_path=str(
                        self.database_path
                    ),
                )
            ),
            2,
        )

    def test_invalid_inputs_fail_before_database_access(
        self,
    ):
        connection_factory = Mock(
            side_effect=AssertionError(
                "database should not be opened"
            )
        )

        invalid_calls = (
            lambda: (
                knowledge_service
                .create_knowledge_document(
                    title="",
                    filename="report.pdf",
                    object_key="knowledge/report.pdf",
                    file_hash="a" * 64,
                    file_size=1,
                    db_path=str(
                        self.database_path
                    ),
                    connection_factory=(
                        connection_factory
                    ),
                )
            ),
            lambda: (
                knowledge_service
                .create_knowledge_document(
                    title="Report",
                    filename="report.pdf",
                    object_key="knowledge/report.pdf",
                    file_hash="unsafe",
                    file_size=1,
                    db_path=str(
                        self.database_path
                    ),
                    connection_factory=(
                        connection_factory
                    ),
                )
            ),
            lambda: (
                knowledge_service
                .list_knowledge_documents(
                    limit=0,
                    db_path=str(
                        self.database_path
                    ),
                    connection_factory=(
                        connection_factory
                    ),
                )
            ),
            lambda: (
                knowledge_service
                .set_knowledge_document_enabled(
                    "knowledge-1",
                    1,
                    db_path=str(
                        self.database_path
                    ),
                    connection_factory=(
                        connection_factory
                    ),
                )
            ),
        )

        for operation in invalid_calls:
            with self.subTest(
                operation=operation
            ):
                with self.assertRaises(
                    knowledge_service
                    .KnowledgeMetadataError
                ):
                    operation()

        connection_factory.assert_not_called()

    def test_ready_status_updates_counts(self):
        self.create_record()

        ready = (
            knowledge_service
            .update_knowledge_document_status(
                "knowledge-1",
                "ready",
                page_count=7,
                chunk_count=21,
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertIsNotNone(ready)
        self.assertEqual(
            ready["status"],
            "ready",
        )
        self.assertEqual(
            ready["page_count"],
            7,
        )
        self.assertEqual(
            ready["chunk_count"],
            21,
        )

    def test_non_ready_status_preserves_counts(self):
        self.create_record()
        knowledge_service.update_knowledge_document_status(
            "knowledge-1",
            "ready",
            page_count=4,
            chunk_count=8,
            db_path=str(
                self.database_path
            ),
        )

        failed = (
            knowledge_service
            .update_knowledge_document_status(
                "knowledge-1",
                "failed",
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertEqual(
            failed["status"],
            "failed",
        )
        self.assertEqual(
            failed["page_count"],
            4,
        )
        self.assertEqual(
            failed["chunk_count"],
            8,
        )

    def test_invalid_status_counts_are_rejected(self):
        self.create_record()

        invalid_operations = (
            lambda: (
                knowledge_service
                .update_knowledge_document_status(
                    "knowledge-1",
                    "ready",
                    db_path=str(
                        self.database_path
                    ),
                )
            ),
            lambda: (
                knowledge_service
                .update_knowledge_document_status(
                    "knowledge-1",
                    "failed",
                    page_count=1,
                    chunk_count=1,
                    db_path=str(
                        self.database_path
                    ),
                )
            ),
            lambda: (
                knowledge_service
                .update_knowledge_document_status(
                    "knowledge-1",
                    "unsafe",
                    db_path=str(
                        self.database_path
                    ),
                )
            ),
        )

        for operation in invalid_operations:
            with self.subTest(
                operation=operation
            ):
                with self.assertRaises(
                    knowledge_service
                    .KnowledgeMetadataError
                ):
                    operation()

    def test_enable_disable_and_filters(self):
        self.create_record()
        self.create_record(
            knowledge_id="knowledge-2",
            title="Second Guide",
            filename="second.pdf",
            object_key="knowledge/second.pdf",
            file_hash="b" * 64,
        )

        disabled = (
            knowledge_service
            .set_knowledge_document_enabled(
                "knowledge-1",
                False,
                db_path=str(
                    self.database_path
                ),
            )
        )
        knowledge_service.update_knowledge_document_status(
            "knowledge-2",
            "ready",
            page_count=2,
            chunk_count=5,
            db_path=str(
                self.database_path
            ),
        )

        self.assertFalse(
            disabled["is_enabled"]
        )

        enabled = (
            knowledge_service
            .list_knowledge_documents(
                enabled=True,
                db_path=str(
                    self.database_path
                ),
            )
        )
        ready = (
            knowledge_service
            .list_knowledge_documents(
                status="ready",
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertEqual(
            [
                item["knowledge_id"]
                for item in enabled
            ],
            ["knowledge-2"],
        )
        self.assertEqual(
            [
                item["knowledge_id"]
                for item in ready
            ],
            ["knowledge-2"],
        )

    def test_missing_updates_return_none(self):
        status = (
            knowledge_service
            .update_knowledge_document_status(
                "missing",
                "failed",
                db_path=str(
                    self.database_path
                ),
            )
        )
        enabled = (
            knowledge_service
            .set_knowledge_document_enabled(
                "missing",
                False,
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertIsNone(status)
        self.assertIsNone(enabled)

    def test_delete_is_idempotent(self):
        self.create_record()

        first = (
            knowledge_service
            .delete_knowledge_document(
                "knowledge-1",
                db_path=str(
                    self.database_path
                ),
            )
        )
        second = (
            knowledge_service
            .delete_knowledge_document(
                "knowledge-1",
                db_path=str(
                    self.database_path
                ),
            )
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertIsNone(
            knowledge_service
            .get_knowledge_document(
                "knowledge-1",
                db_path=str(
                    self.database_path
                ),
            )
        )

    def test_database_errors_are_sanitized(self):
        def failing_connection_factory(_):
            raise RuntimeError(
                "postgresql://secret-user:secret-pass@host/db"
            )

        with self.assertRaises(
            knowledge_service.KnowledgeMetadataError
        ) as captured:
            knowledge_service.get_knowledge_document(
                "knowledge-1",
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    failing_connection_factory
                ),
            )

        message = str(captured.exception)

        self.assertEqual(
            message,
            "Knowledge metadata read failed.",
        )
        self.assertNotIn(
            "secret-user",
            message,
        )
        self.assertNotIn(
            "secret-pass",
            message,
        )


if __name__ == "__main__":
    unittest.main()
