import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from unittest.mock import (
    Mock,
    patch,
)

from app.services.document_object_service import (
    store_document_bytes,
)
from app.services.document_service import (
    calculate_file_hash,
)
from app.services.export_service import (
    BackupValidationError,
    MANIFEST_NAME,
    create_full_chat_backup,
    restore_full_chat_backup,
)
from app.storage.document_storage import (
    LocalDocumentStorage,
)


class FakeRAG:
    def __init__(
        self,
        *,
        chunks=2,
    ):
        self.chunks = chunks
        self.indexed_contents = []
        self.temporary_paths = []
        self.deleted_chat_ids = []

    def add_pdf(
        self,
        *,
        file_path,
        chat_id,
        document_id,
    ):
        path = Path(file_path)

        self.temporary_paths.append(
            path
        )

        self.indexed_contents.append(
            path.read_bytes()
        )

        return {
            "pages": 1,
            "chunks": self.chunks,
            "chat_id": chat_id,
            "document_id": (
                document_id
            ),
        }

    def delete_chat(
        self,
        chat_id,
    ):
        self.deleted_chat_ids.append(
            chat_id
        )

        return {
            "deleted_chunks": 0,
        }


def build_minimal_archive() -> bytes:
    """Build a valid ZIP shell for mocked restore tests."""
    stream = BytesIO()

    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=(
            zipfile.ZIP_DEFLATED
        ),
    ) as archive:
        archive.writestr(
            MANIFEST_NAME,
            "{}",
        )

    return stream.getvalue()


def restore_manifest():
    return {
        "schema_version": 1,
        "application": "onkar-ai",
        "exported_at": (
            "2026-07-20T00:00:00Z"
        ),
        "chat": {
            "title": "Restored chat",
        },
        "model": None,
        "messages": [],
        "warnings": [],
    }


class DurableBackupStorageTests(
    unittest.TestCase
):
    def test_export_reads_pdf_from_object_storage(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = (
                LocalDocumentStorage(
                    Path(directory)
                    / "objects"
                )
            )

            content = (
                b"%PDF-1.4\n"
                b"durable-export\n"
                b"%%EOF"
            )

            file_hash = (
                calculate_file_hash(
                    content
                )
            )

            object_key = (
                store_document_bytes(
                    chat_id=12,
                    document_id="doc-1",
                    filename="report.pdf",
                    file_hash=file_hash,
                    data=content,
                    storage=storage,
                )
            )

            document = {
                "document_id": (
                    "doc-1"
                ),
                "chat_id": 12,
                "filename": (
                    "report.pdf"
                ),
                "file_path": (
                    object_key
                ),
                "file_hash": (
                    file_hash
                ),
                "file_size": len(
                    content
                ),
                "page_count": 1,
                "chunk_count": 2,
                "status": "ready",
                "is_selected": True,
            }

            backup_path = None

            try:
                with ExitStack() as stack:
                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "get_document_storage",
                            return_value=(
                                storage
                            ),
                        )
                    )

                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "_find_chat",
                            return_value={
                                "id": 12,
                                "title": (
                                    "Durable"
                                ),
                            },
                        )
                    )

                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "_build_backup_messages",
                            return_value=[],
                        )
                    )

                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "list_documents",
                            return_value=[
                                document
                            ],
                        )
                    )

                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "_build_manifest",
                            return_value={
                                "documents": [
                                    {
                                        "filename": (
                                            "report.pdf"
                                        )
                                    }
                                ]
                            },
                        )
                    )

                    (
                        backup_path,
                        download_name,
                    ) = (
                        create_full_chat_backup(
                            12
                        )
                    )

                self.assertTrue(
                    download_name.endswith(
                        ".zip"
                    )
                )

                with zipfile.ZipFile(
                    backup_path,
                    mode="r",
                ) as archive:
                    self.assertIn(
                        MANIFEST_NAME,
                        archive.namelist(),
                    )

                    self.assertEqual(
                        archive.read(
                            "documents/"
                            "report.pdf"
                        ),
                        content,
                    )

            finally:
                if backup_path is not None:
                    Path(
                        backup_path
                    ).unlink(
                        missing_ok=True
                    )

    def test_restore_writes_object_and_indexes_temp_pdf(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = (
                LocalDocumentStorage(
                    Path(directory)
                    / "objects"
                )
            )

            content = (
                b"%PDF-1.4\n"
                b"durable-restore\n"
                b"%%EOF"
            )

            file_hash = (
                calculate_file_hash(
                    content
                )
            )

            payloads = [
                {
                    "filename": (
                        "notes.pdf"
                    ),
                    "content": content,
                    "file_hash": (
                        file_hash
                    ),
                    "file_size": len(
                        content
                    ),
                    "is_selected": (
                        True
                    ),
                }
            ]

            fake_rag = FakeRAG()
            created_documents = {}

            def create_document(
                **arguments,
            ):
                document = {
                    **arguments,
                    "status": (
                        "processing"
                    ),
                    "is_selected": (
                        True
                    ),
                }

                created_documents[
                    arguments[
                        "document_id"
                    ]
                ] = document

                return document

            def mark_ready(
                *,
                document_id,
                chat_id,
                page_count,
                chunk_count,
            ):
                document = dict(
                    created_documents[
                        document_id
                    ]
                )

                document.update(
                    {
                        "chat_id": (
                            chat_id
                        ),
                        "page_count": (
                            page_count
                        ),
                        "chunk_count": (
                            chunk_count
                        ),
                        "status": (
                            "ready"
                        ),
                    }
                )

                return document

            with ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "get_document_storage",
                        return_value=(
                            storage
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "RAGService",
                        return_value=(
                            fake_rag
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "_read_and_validate_manifest",
                        return_value=(
                            restore_manifest()
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "_read_document_payloads",
                        return_value=(
                            payloads
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "restore_chat_backup",
                        return_value={
                            "chat_id": 55,
                            "warnings": [],
                        },
                    )
                )

                create_mock = (
                    stack.enter_context(
                        patch(
                            "app.services."
                            "export_service."
                            "create_document",
                            side_effect=(
                                create_document
                            ),
                        )
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "mark_document_ready",
                        side_effect=(
                            mark_ready
                        ),
                    )
                )

                result = (
                    restore_full_chat_backup(
                        build_minimal_archive()
                    )
                )

            self.assertEqual(
                result[
                    "document_count"
                ],
                1,
            )

            self.assertEqual(
                result["total_pages"],
                1,
            )

            self.assertEqual(
                result["total_chunks"],
                2,
            )

            self.assertEqual(
                fake_rag.indexed_contents,
                [content],
            )

            for temporary_path in (
                fake_rag.temporary_paths
            ):
                self.assertFalse(
                    temporary_path.exists()
                )

            arguments = (
                create_mock.call_args.kwargs
            )

            object_key = arguments[
                "file_path"
            ]

            self.assertTrue(
                storage.exists(
                    object_key
                )
            )

            self.assertEqual(
                storage.get_bytes(
                    object_key
                ),
                content,
            )

            self.assertNotIn(
                "\\",
                object_key,
            )

    def test_restore_failure_removes_stored_objects(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = (
                LocalDocumentStorage(
                    Path(directory)
                    / "objects"
                )
            )

            content = (
                b"%PDF-1.4\n"
                b"rollback\n"
                b"%%EOF"
            )

            payloads = [
                {
                    "filename": (
                        "rollback.pdf"
                    ),
                    "content": content,
                    "file_hash": (
                        calculate_file_hash(
                            content
                        )
                    ),
                    "file_size": len(
                        content
                    ),
                    "is_selected": (
                        True
                    ),
                }
            ]

            fake_rag = FakeRAG(
                chunks=0
            )

            delete_records = Mock()
            delete_chat = Mock()

            def create_document(
                **arguments,
            ):
                return {
                    **arguments,
                    "status": (
                        "processing"
                    ),
                    "is_selected": (
                        True
                    ),
                }

            with ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "get_document_storage",
                        return_value=(
                            storage
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "RAGService",
                        return_value=(
                            fake_rag
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "_read_and_validate_manifest",
                        return_value=(
                            restore_manifest()
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "_read_document_payloads",
                        return_value=(
                            payloads
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "restore_chat_backup",
                        return_value={
                            "chat_id": 77,
                            "warnings": [],
                        },
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "create_document",
                        side_effect=(
                            create_document
                        ),
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "delete_chat_documents",
                        delete_records,
                    )
                )

                stack.enter_context(
                    patch(
                        "app.services."
                        "export_service."
                        "delete_chat",
                        delete_chat,
                    )
                )

                with self.assertRaises(
                    BackupValidationError
                ):
                    restore_full_chat_backup(
                        build_minimal_archive()
                    )

            remaining_files = [
                item
                for item
                in storage.root.rglob(
                    "*"
                )
                if item.is_file()
            ]

            self.assertEqual(
                remaining_files,
                [],
            )

            self.assertEqual(
                fake_rag.deleted_chat_ids,
                [77],
            )

            delete_records.assert_called_once_with(
                77
            )

            delete_chat.assert_called_once_with(
                77
            )


if __name__ == "__main__":
    unittest.main()
