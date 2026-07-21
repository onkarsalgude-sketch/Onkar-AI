from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api import documents as documents_api
from app.services import document_service
from app.services.rag_service import RAGService


def document_fixture(
    *,
    status: str = "ready",
) -> dict:
    return {
        "document_id": "document-123",
        "chat_id": 7,
        "filename": "notes.pdf",
        "file_path": (
            "chats/7/documents/"
            "document-123/notes.pdf"
        ),
        "file_hash": "abc123",
        "file_size": 100,
        "page_count": 1,
        "chunk_count": 2,
        "status": status,
        "is_selected": True,
        "uploaded_at": "2026-07-20T00:00:00",
        "updated_at": "2026-07-20T00:00:00",
    }


class DocumentDeletingStatusTests(
    unittest.TestCase
):
    def test_mark_deleting_updates_status_and_selection(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "documents.db"
            )

            connection = sqlite3.connect(
                database_path
            )

            connection.execute(
                """
                CREATE TABLE documents (
                    document_id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    page_count INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    is_selected INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                INSERT INTO documents (
                    document_id,
                    chat_id,
                    filename,
                    file_path,
                    file_hash,
                    file_size,
                    page_count,
                    chunk_count,
                    status,
                    is_selected,
                    uploaded_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "document-123",
                    7,
                    "notes.pdf",
                    "object-key",
                    "abc123",
                    100,
                    1,
                    2,
                    "ready",
                    1,
                    "2026-07-20T00:00:00",
                    "2026-07-20T00:00:00",
                ),
            )

            connection.commit()
            connection.close()

            def connection_factory(*args, **kwargs):
                return sqlite3.connect(
                    database_path
                )

            with patch.object(
                document_service,
                "get_runtime_connection",
                side_effect=connection_factory,
            ):
                result = (
                    document_service
                    .mark_document_deleting(
                        document_id="document-123",
                        chat_id=7,
                    )
                )

            self.assertIsNotNone(result)
            self.assertEqual(
                result["status"],
                "deleting",
            )
            self.assertFalse(
                result["is_selected"]
            )


class DocumentDeleteLifecycleTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_delete_uses_resumable_order(
        self,
    ):
        document = document_fixture()
        deleting = document_fixture(
            status="deleting"
        )
        events = []

        with (
            patch.object(
                documents_api,
                "get_document_by_filename",
                return_value=document,
            ),
            patch.object(
                documents_api,
                "mark_document_deleting",
                side_effect=lambda **kwargs: (
                    events.append("mark")
                    or deleting
                ),
            ),
            patch.object(
                documents_api,
                "delete_document_object",
                side_effect=lambda value: (
                    events.append("object")
                    or True
                ),
            ),
            patch.object(
                documents_api.rag,
                "delete_document",
                side_effect=lambda **kwargs: (
                    events.append("rag")
                    or {
                        "deleted_chunks": 2,
                    }
                ),
            ) as delete_vectors,
            patch.object(
                documents_api,
                "delete_document_record",
                side_effect=lambda **kwargs: (
                    events.append("record")
                    or True
                ),
            ),
        ):
            result = await (
                documents_api.delete_document(
                    "notes.pdf",
                    7,
                )
            )

        self.assertEqual(
            events,
            [
                "mark",
                "object",
                "rag",
                "record",
            ],
        )

        delete_vectors.assert_called_once_with(
            document_id="document-123",
            filename="notes.pdf",
            chat_id=7,
        )

        self.assertEqual(
            result["status"],
            "deleted",
        )
        self.assertFalse(
            result["already_deleted"]
        )
        self.assertTrue(
            result["file_deleted"]
        )
        self.assertTrue(
            result["record_deleted"]
        )
        self.assertEqual(
            result["deleted_chunks"],
            2,
        )

    async def test_retry_continues_when_object_is_missing(
        self,
    ):
        deleting = document_fixture(
            status="deleting"
        )

        with (
            patch.object(
                documents_api,
                "get_document_by_filename",
                return_value=deleting,
            ),
            patch.object(
                documents_api,
                "mark_document_deleting",
                return_value=deleting,
            ),
            patch.object(
                documents_api,
                "delete_document_object",
                return_value=False,
            ),
            patch.object(
                documents_api.rag,
                "delete_document",
                return_value={
                    "deleted_chunks": 0,
                },
            ),
            patch.object(
                documents_api,
                "delete_document_record",
                return_value=True,
            ),
        ):
            result = await (
                documents_api.delete_document(
                    "notes.pdf",
                    7,
                )
            )

        self.assertFalse(
            result["file_deleted"]
        )
        self.assertTrue(
            result["file_missing"]
        )
        self.assertTrue(
            result["record_deleted"]
        )
        self.assertFalse(
            result["already_deleted"]
        )

    async def test_repeated_delete_is_idempotent(
        self,
    ):
        with (
            patch.object(
                documents_api,
                "get_document_by_filename",
                return_value=None,
            ),
            patch.object(
                documents_api,
                "mark_document_deleting",
            ) as mark_deleting,
            patch.object(
                documents_api,
                "delete_document_object",
            ) as delete_object,
            patch.object(
                documents_api.rag,
                "delete_pdf",
                return_value={
                    "deleted_chunks": 0,
                },
            ) as delete_vectors,
            patch.object(
                documents_api,
                "delete_document_record",
            ) as delete_record,
        ):
            result = await (
                documents_api.delete_document(
                    "notes.pdf",
                    7,
                )
            )

        mark_deleting.assert_not_called()
        delete_object.assert_not_called()
        delete_record.assert_not_called()

        delete_vectors.assert_called_once_with(
            "notes.pdf",
            chat_id=7,
        )

        self.assertTrue(
            result["already_deleted"]
        )
        self.assertEqual(
            result["status"],
            "deleted",
        )
        self.assertEqual(
            result["message"],
            "Document already deleted",
        )

    async def test_rag_failure_keeps_metadata_for_retry(
        self,
    ):
        document = document_fixture()
        deleting = document_fixture(
            status="deleting"
        )

        with (
            patch.object(
                documents_api,
                "get_document_by_filename",
                return_value=document,
            ),
            patch.object(
                documents_api,
                "mark_document_deleting",
                return_value=deleting,
            ),
            patch.object(
                documents_api,
                "delete_document_object",
                return_value=True,
            ),
            patch.object(
                documents_api.rag,
                "delete_document",
                side_effect=RuntimeError(
                    "temporary failure"
                ),
            ),
            patch.object(
                documents_api,
                "delete_document_record",
            ) as delete_record,
        ):
            with self.assertRaises(
                HTTPException
            ) as captured:
                await documents_api.delete_document(
                    "notes.pdf",
                    7,
                )

        self.assertEqual(
            captured.exception.status_code,
            503,
        )

        delete_record.assert_not_called()

    async def test_preview_rejects_deleting_document(
        self,
    ):
        deleting = document_fixture(
            status="deleting"
        )

        with (
            patch.object(
                documents_api,
                "get_document_by_filename",
                return_value=deleting,
            ),
            patch.object(
                documents_api,
                "read_document_bytes",
            ) as read_bytes,
        ):
            with self.assertRaises(
                HTTPException
            ) as captured:
                await documents_api.preview_pdf(
                    "notes.pdf",
                    7,
                )

        self.assertEqual(
            captured.exception.status_code,
            409,
        )

        read_bytes.assert_not_called()


class RAGDocumentDeleteTests(
    unittest.TestCase
):
    def test_pgvector_delete_uses_document_id(
        self,
    ):
        service = object.__new__(
            RAGService
        )

        service.settings = SimpleNamespace(
            is_pgvector=True
        )

        service.store = Mock()
        service.store.delete_document.return_value = 3

        result = service.delete_document(
            document_id="document-123",
            filename="notes.pdf",
            chat_id=7,
        )

        service.store.delete_document.assert_called_once_with(
            chat_id=7,
            document_id="document-123",
        )

        self.assertEqual(
            result["deleted_chunks"],
            3,
        )

        self.assertEqual(
            result["document_id"],
            "document-123",
        )

    def test_chroma_delete_preserves_filename_fallback(
        self,
    ):
        service = object.__new__(
            RAGService
        )

        service.settings = SimpleNamespace(
            is_pgvector=False
        )

        expected = {
            "filename": "notes.pdf",
            "chat_id": 7,
            "deleted_chunks": 2,
            "remaining_chunks": 0,
        }

        with patch.object(
            service,
            "delete_pdf",
            return_value=expected,
        ) as delete_pdf:
            result = service.delete_document(
                document_id="document-123",
                filename="notes.pdf",
                chat_id=7,
            )

        delete_pdf.assert_called_once_with(
            "notes.pdf",
            7,
        )

        self.assertEqual(
            result,
            expected,
        )


if __name__ == "__main__":
    unittest.main()
