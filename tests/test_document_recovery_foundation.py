from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from app.config.document_recovery import (
    DEFAULT_RECOVERY_BATCH_SIZE,
    DEFAULT_RECOVERY_ENABLED,
    DEFAULT_STALE_AFTER_SECONDS,
    DocumentRecoveryConfigurationError,
    DocumentRecoverySettings,
    load_document_recovery_settings,
)
from app.services import document_service
from app.services.document_recovery_service import (
    scan_stuck_documents,
)


def document_record(
    document_id: str,
    *,
    status: str,
    updated_at: str,
) -> dict:
    return {
        "document_id": document_id,
        "chat_id": 7,
        "filename": f"{document_id}.pdf",
        "file_path": f"objects/{document_id}",
        "file_hash": "hash",
        "file_size": 100,
        "page_count": 1,
        "chunk_count": 2,
        "status": status,
        "is_selected": True,
        "uploaded_at": updated_at,
        "updated_at": updated_at,
    }


class DocumentRecoveryConfigurationTests(
    unittest.TestCase
):
    def test_defaults_are_safe(
        self,
    ):
        settings = (
            load_document_recovery_settings(
                {}
            )
        )

        self.assertEqual(
            settings.enabled,
            DEFAULT_RECOVERY_ENABLED,
        )

        self.assertEqual(
            settings.stale_after_seconds,
            DEFAULT_STALE_AFTER_SECONDS,
        )

        self.assertEqual(
            settings.batch_size,
            DEFAULT_RECOVERY_BATCH_SIZE,
        )

    def test_environment_overrides_are_loaded(
        self,
    ):
        settings = (
            load_document_recovery_settings(
                {
                    "DOCUMENT_RECOVERY_ENABLED": "false",
                    "DOCUMENT_RECOVERY_STALE_SECONDS": "1800",
                    "DOCUMENT_RECOVERY_BATCH_SIZE": "40",
                }
            )
        )

        self.assertFalse(
            settings.enabled
        )

        self.assertEqual(
            settings.stale_after_seconds,
            1800,
        )

        self.assertEqual(
            settings.batch_size,
            40,
        )

    def test_invalid_boolean_is_rejected(
        self,
    ):
        with self.assertRaises(
            DocumentRecoveryConfigurationError
        ):
            load_document_recovery_settings(
                {
                    "DOCUMENT_RECOVERY_ENABLED": "maybe",
                }
            )

    def test_invalid_integer_ranges_are_rejected(
        self,
    ):
        invalid_environments = [
            {
                "DOCUMENT_RECOVERY_STALE_SECONDS": "59",
            },
            {
                "DOCUMENT_RECOVERY_BATCH_SIZE": "0",
            },
            {
                "DOCUMENT_RECOVERY_BATCH_SIZE": "101",
            },
        ]

        for environ in invalid_environments:
            with (
                self.subTest(
                    environ=environ
                ),
                self.assertRaises(
                    DocumentRecoveryConfigurationError
                ),
            ):
                load_document_recovery_settings(
                    environ
                )


class DocumentStatusQueryTests(
    unittest.TestCase
):
    def test_status_query_filters_and_orders_documents(
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

            rows = [
                (
                    "ready-one",
                    7,
                    "ready.pdf",
                    "ready-key",
                    "hash",
                    100,
                    1,
                    2,
                    "ready",
                    1,
                    "2026-07-20T09:00:00",
                    "2026-07-20T09:00:00",
                ),
                (
                    "deleting-two",
                    7,
                    "deleting.pdf",
                    "delete-key",
                    "hash",
                    100,
                    1,
                    2,
                    "deleting",
                    0,
                    "2026-07-20T10:00:00",
                    "2026-07-20T10:00:00",
                ),
                (
                    "processing-one",
                    7,
                    "processing.pdf",
                    "process-key",
                    "hash",
                    100,
                    0,
                    0,
                    "processing",
                    1,
                    "2026-07-20T08:00:00",
                    "2026-07-20T08:00:00",
                ),
            ]

            connection.executemany(
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
                rows,
            )

            connection.commit()
            connection.close()

            def connection_factory(
                *args,
                **kwargs,
            ):
                return sqlite3.connect(
                    database_path
                )

            with patch.object(
                document_service,
                "get_runtime_connection",
                side_effect=connection_factory,
            ):
                documents = (
                    document_service
                    .list_documents_by_statuses(
                        (
                            "processing",
                            "deleting",
                        )
                    )
                )

        self.assertEqual(
            [
                document["document_id"]
                for document in documents
            ],
            [
                "processing-one",
                "deleting-two",
            ],
        )


class DocumentRecoveryScanTests(
    unittest.TestCase
):
    def test_disabled_scan_does_not_query_database(
        self,
    ):
        query = Mock()

        result = scan_stuck_documents(
            DocumentRecoverySettings(
                enabled=False,
                stale_after_seconds=900,
                batch_size=25,
            ),
            list_documents_fn=query,
        )

        query.assert_not_called()

        self.assertFalse(
            result.enabled
        )

        self.assertEqual(
            result.candidate_count,
            0,
        )

    def test_scan_classifies_stale_recent_and_invalid_rows(
        self,
    ):
        documents = [
            document_record(
                "stale-processing",
                status="processing",
                updated_at=(
                    "2026-07-21T09:00:00+00:00"
                ),
            ),
            document_record(
                "recent-deleting",
                status="deleting",
                updated_at=(
                    "2026-07-21T09:55:00+00:00"
                ),
            ),
            document_record(
                "invalid-time",
                status="processing",
                updated_at="not-a-date",
            ),
        ]

        result = scan_stuck_documents(
            DocumentRecoverySettings(
                enabled=True,
                stale_after_seconds=900,
                batch_size=25,
            ),
            now=datetime(
                2026,
                7,
                21,
                10,
                0,
                tzinfo=timezone.utc,
            ),
            list_documents_fn=(
                lambda statuses: documents
            ),
        )

        self.assertEqual(
            result.total_examined,
            3,
        )

        self.assertEqual(
            result.recent_count,
            1,
        )

        self.assertEqual(
            result.invalid_timestamp_count,
            1,
        )

        self.assertEqual(
            [
                candidate.document_id
                for candidate in result.candidates
            ],
            [
                "stale-processing",
            ],
        )

    def test_batch_limit_selects_oldest_documents_first(
        self,
    ):
        documents = [
            document_record(
                "newer",
                status="processing",
                updated_at=(
                    "2026-07-21T08:00:00+00:00"
                ),
            ),
            document_record(
                "oldest",
                status="deleting",
                updated_at=(
                    "2026-07-21T06:00:00+00:00"
                ),
            ),
            document_record(
                "middle",
                status="processing",
                updated_at=(
                    "2026-07-21T07:00:00+00:00"
                ),
            ),
        ]

        result = scan_stuck_documents(
            DocumentRecoverySettings(
                enabled=True,
                stale_after_seconds=60,
                batch_size=2,
            ),
            now=datetime(
                2026,
                7,
                21,
                10,
                0,
                tzinfo=timezone.utc,
            ),
            list_documents_fn=(
                lambda statuses: documents
            ),
        )

        self.assertEqual(
            [
                candidate.document_id
                for candidate in result.candidates
            ],
            [
                "oldest",
                "middle",
            ],
        )

        self.assertEqual(
            result.deferred_count,
            1,
        )


if __name__ == "__main__":
    unittest.main()
