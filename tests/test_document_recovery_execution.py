from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_recovery_service import (
    recover_stuck_documents,
)


NOW = datetime(
    2026,
    7,
    21,
    12,
    0,
    tzinfo=timezone.utc,
)

STALE_TIME = (
    "2026-07-21T10:00:00+00:00"
)


def recovery_document(
    document_id: str,
    *,
    status: str,
    updated_at: str = STALE_TIME,
) -> dict:
    return {
        "document_id": document_id,
        "chat_id": 11,
        "filename": f"{document_id}.pdf",
        "file_path": f"documents/{document_id}.pdf",
        "file_hash": "hash",
        "file_size": 100,
        "page_count": 0,
        "chunk_count": 0,
        "status": status,
        "is_selected": (
            status != "deleting"
        ),
        "uploaded_at": updated_at,
        "updated_at": updated_at,
    }


def enabled_settings() -> DocumentRecoverySettings:
    return DocumentRecoverySettings(
        enabled=True,
        stale_after_seconds=900,
        batch_size=25,
    )


@contextmanager
def temporary_pdf(
    data: bytes,
    filename: str,
):
    self_path = Path(
        f"/temporary/{filename}"
    )

    yield self_path


class DocumentRecoveryExecutionTests(
    unittest.TestCase
):
    def test_processing_document_is_reindexed_and_marked_ready(
        self,
    ):
        document = recovery_document(
            "processing-success",
            status="processing",
        )

        rag = Mock()

        rag.add_pdf.return_value = {
            "pages": 3,
            "chunks": 8,
        }

        mark_ready = Mock(
            return_value={
                **document,
                "status": "ready",
                "page_count": 3,
                "chunk_count": 8,
            }
        )

        result = recover_stuck_documents(
            enabled_settings(),
            rag=rag,
            now=NOW,
            list_documents_fn=(
                lambda statuses: [document]
            ),
            get_document_fn=(
                lambda **kwargs: document
            ),
            read_document_bytes_fn=(
                lambda value: b"%PDF"
            ),
            materialize_pdf_bytes_fn=(
                temporary_pdf
            ),
            mark_document_ready_fn=(
                mark_ready
            ),
        )

        self.assertEqual(
            result.processing_recovered_count,
            1,
        )

        self.assertEqual(
            result.failure_count,
            0,
        )

        rag.add_pdf.assert_called_once()

        mark_ready.assert_called_once_with(
            document_id=(
                "processing-success"
            ),
            chat_id=11,
            page_count=3,
            chunk_count=8,
        )

    def test_missing_processing_object_is_marked_failed(
        self,
    ):
        document = recovery_document(
            "processing-missing",
            status="processing",
        )

        class DocumentNotFoundError(
            RuntimeError
        ):
            pass

        mark_failed = Mock(
            return_value={
                **document,
                "status": "failed",
            }
        )

        result = recover_stuck_documents(
            enabled_settings(),
            rag=Mock(),
            now=NOW,
            list_documents_fn=(
                lambda statuses: [document]
            ),
            get_document_fn=(
                lambda **kwargs: document
            ),
            read_document_bytes_fn=(
                Mock(
                    side_effect=(
                        DocumentNotFoundError(
                            "Object missing"
                        )
                    )
                )
            ),
            mark_document_failed_fn=(
                mark_failed
            ),
        )

        self.assertEqual(
            result.results[0].outcome,
            "processing_failed_missing_object",
        )

        mark_failed.assert_called_once_with(
            document_id=(
                "processing-missing"
            ),
            chat_id=11,
        )

    def test_transient_processing_failure_remains_retryable(
        self,
    ):
        document = recovery_document(
            "processing-transient",
            status="processing",
        )

        mark_failed = Mock()

        result = recover_stuck_documents(
            enabled_settings(),
            rag=Mock(),
            now=NOW,
            list_documents_fn=(
                lambda statuses: [document]
            ),
            get_document_fn=(
                lambda **kwargs: document
            ),
            read_document_bytes_fn=(
                Mock(
                    side_effect=RuntimeError(
                        "Temporary storage failure"
                    )
                )
            ),
            mark_document_failed_fn=(
                mark_failed
            ),
        )

        self.assertEqual(
            result.results[0].outcome,
            "processing_retry_failed",
        )

        mark_failed.assert_not_called()

    def test_deleting_document_cleanup_completes(
        self,
    ):
        document = recovery_document(
            "deleting-success",
            status="deleting",
        )

        rag = Mock()

        rag.delete_document.return_value = {
            "deleted_chunks": 4,
            "remaining_chunks": 0,
        }

        delete_object = Mock(
            return_value=False
        )

        delete_record = Mock(
            return_value=True
        )

        result = recover_stuck_documents(
            enabled_settings(),
            rag=rag,
            now=NOW,
            list_documents_fn=(
                lambda statuses: [document]
            ),
            get_document_fn=(
                lambda **kwargs: document
            ),
            delete_document_object_fn=(
                delete_object
            ),
            delete_document_record_fn=(
                delete_record
            ),
        )

        self.assertEqual(
            result.deleting_completed_count,
            1,
        )

        delete_object.assert_called_once_with(
            document
        )

        rag.delete_document.assert_called_once_with(
            document_id=(
                "deleting-success"
            ),
            filename=(
                "deleting-success.pdf"
            ),
            chat_id=11,
        )

        delete_record.assert_called_once()

    def test_vector_failure_preserves_deleting_metadata(
        self,
    ):
        document = recovery_document(
            "deleting-retry",
            status="deleting",
        )

        rag = Mock()

        rag.delete_document.side_effect = (
            RuntimeError(
                "Temporary vector failure"
            )
        )

        delete_record = Mock()

        result = recover_stuck_documents(
            enabled_settings(),
            rag=rag,
            now=NOW,
            list_documents_fn=(
                lambda statuses: [document]
            ),
            get_document_fn=(
                lambda **kwargs: document
            ),
            delete_document_object_fn=(
                Mock(return_value=True)
            ),
            delete_document_record_fn=(
                delete_record
            ),
        )

        self.assertEqual(
            result.results[0].outcome,
            "deletion_retry_failed",
        )

        delete_record.assert_not_called()

    def test_changed_document_is_skipped_safely(
        self,
    ):
        scanned_document = recovery_document(
            "changed-document",
            status="processing",
        )

        current_document = {
            **scanned_document,
            "updated_at": (
                "2026-07-21T11:59:00+00:00"
            ),
        }

        rag = Mock()
        read_bytes = Mock()

        result = recover_stuck_documents(
            enabled_settings(),
            rag=rag,
            now=NOW,
            list_documents_fn=(
                lambda statuses: [
                    scanned_document
                ]
            ),
            get_document_fn=(
                lambda **kwargs: (
                    current_document
                )
            ),
            read_document_bytes_fn=(
                read_bytes
            ),
        )

        self.assertEqual(
            result.results[0].outcome,
            "skipped_changed",
        )

        read_bytes.assert_not_called()
        rag.add_pdf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
