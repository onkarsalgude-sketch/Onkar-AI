import unittest
from unittest.mock import Mock, patch

from app.services import knowledge_object_service
from app.storage.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
)


PDF_BYTES = (
    b"%PDF-1.7\n"
    b"knowledge object test"
)
FILE_HASH = "a" * 64


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.put_calls = []
        self.get_calls = []
        self.delete_calls = []

    def put_bytes(
        self,
        key,
        data,
        *,
        content_type,
    ):
        self.put_calls.append(
            {
                "key": key,
                "data": data,
                "content_type": (
                    content_type
                ),
            }
        )
        self.objects[key] = bytes(data)
        return key

    def get_bytes(self, key):
        self.get_calls.append(key)

        if key not in self.objects:
            raise DocumentNotFoundError(
                "private backend key missing"
            )

        return self.objects[key]

    def delete(self, key):
        self.delete_calls.append(key)
        return (
            self.objects.pop(
                key,
                None,
            )
            is not None
        )


class KnowledgeObjectServiceTests(
    unittest.TestCase
):
    def test_key_uses_dedicated_namespace(
        self,
    ):
        key = (
            knowledge_object_service
            .build_knowledge_object_key(
                knowledge_id=(
                    "knowledge-1"
                ),
                filename="../Guide.pdf",
                file_hash=FILE_HASH.upper(),
            )
        )

        self.assertEqual(
            key,
            (
                "knowledge/documents/"
                "knowledge-1/"
                f"{FILE_HASH}/"
                "Guide.pdf"
            ),
        )
        self.assertFalse(
            key.startswith("chats/")
        )

    def test_store_round_trip_and_delete(
        self,
    ):
        storage = FakeStorage()
        key = (
            knowledge_object_service
            .store_knowledge_pdf_bytes(
                knowledge_id=(
                    "knowledge-1"
                ),
                filename="Guide.pdf",
                file_hash=FILE_HASH,
                data=PDF_BYTES,
                storage=storage,
            )
        )
        record = {
            "object_key": key
        }

        self.assertEqual(
            storage.put_calls,
            [
                {
                    "key": key,
                    "data": PDF_BYTES,
                    "content_type": (
                        "application/pdf"
                    ),
                }
            ],
        )
        self.assertEqual(
            knowledge_object_service
            .read_knowledge_pdf_bytes(
                record,
                storage=storage,
            ),
            PDF_BYTES,
        )
        self.assertTrue(
            knowledge_object_service
            .delete_knowledge_pdf_object(
                record,
                storage=storage,
            )
        )
        self.assertFalse(
            knowledge_object_service
            .delete_knowledge_pdf_object(
                record,
                storage=storage,
            )
        )

    def test_invalid_inputs_stop_before_backend(
        self,
    ):
        storage = Mock()
        operations = (
            lambda: (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "../unsafe"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                    data=PDF_BYTES,
                    storage=storage,
                )
            ),
            lambda: (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.txt",
                    file_hash=FILE_HASH,
                    data=PDF_BYTES,
                    storage=storage,
                )
            ),
            lambda: (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash="unsafe",
                    data=PDF_BYTES,
                    storage=storage,
                )
            ),
            lambda: (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                    data=b"not a pdf",
                    storage=storage,
                )
            ),
        )

        for operation in operations:
            with self.subTest(
                operation=operation
            ):
                with self.assertRaises(
                    knowledge_object_service
                    .KnowledgeObjectStorageError
                ):
                    operation()

        storage.put_bytes.assert_not_called()

    def test_read_rejects_chat_object_key(
        self,
    ):
        storage = Mock()

        with self.assertRaises(
            knowledge_object_service
            .KnowledgeObjectStorageError
        ):
            (
                knowledge_object_service
                .read_knowledge_pdf_bytes(
                    {
                        "object_key": (
                            "chats/1/documents/"
                            "doc/hash/Guide.pdf"
                        )
                    },
                    storage=storage,
                )
            )

        storage.get_bytes.assert_not_called()

    def test_missing_read_has_specific_safe_error(
        self,
    ):
        storage = Mock()
        storage.get_bytes.side_effect = (
            DocumentNotFoundError(
                "r2://private-bucket/key"
            )
        )
        record = {
            "object_key": (
                knowledge_object_service
                .build_knowledge_object_key(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                )
            )
        }

        with self.assertRaises(
            knowledge_object_service
            .KnowledgeObjectNotFoundError
        ) as captured:
            (
                knowledge_object_service
                .read_knowledge_pdf_bytes(
                    record,
                    storage=storage,
                )
            )

        self.assertEqual(
            str(captured.exception),
            (
                "Knowledge PDF object "
                "was not found."
            ),
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )

    def test_storage_failures_are_sanitized(
        self,
    ):
        storage = Mock()
        storage.put_bytes.side_effect = (
            DocumentStorageError(
                "https://secret@r2.example"
            )
        )

        with self.assertRaises(
            knowledge_object_service
            .KnowledgeObjectStorageError
        ) as captured:
            (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                    data=PDF_BYTES,
                    storage=storage,
                )
            )

        self.assertEqual(
            str(captured.exception),
            (
                "Knowledge object storage "
                "operation failed."
            ),
        )
        self.assertNotIn(
            "secret",
            str(captured.exception),
        )

    def test_read_rejects_corrupt_payload(
        self,
    ):
        storage = Mock(
            get_bytes=Mock(
                return_value=b"corrupt"
            )
        )
        record = {
            "object_key": (
                knowledge_object_service
                .build_knowledge_object_key(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                )
            )
        }

        with self.assertRaises(
            knowledge_object_service
            .KnowledgeObjectStorageError
        ):
            (
                knowledge_object_service
                .read_knowledge_pdf_bytes(
                    record,
                    storage=storage,
                )
            )

    def test_unexpected_backend_key_is_removed(
        self,
    ):
        storage = Mock()
        storage.put_bytes.return_value = (
            "knowledge/documents/"
            "other/hash/Guide.pdf"
        )

        with self.assertRaises(
            knowledge_object_service
            .KnowledgeObjectStorageError
        ):
            (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                    data=PDF_BYTES,
                    storage=storage,
                )
            )

        storage.delete.assert_called_once_with(
            (
                "knowledge/documents/"
                "other/hash/Guide.pdf"
            )
        )

    def test_default_storage_factory_is_used(
        self,
    ):
        storage = FakeStorage()

        with patch.object(
            knowledge_object_service,
            "get_document_storage",
            return_value=storage,
        ) as factory:
            key = (
                knowledge_object_service
                .store_knowledge_pdf_bytes(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="Guide.pdf",
                    file_hash=FILE_HASH,
                    data=PDF_BYTES,
                )
            )

        factory.assert_called_once_with()
        self.assertIn(
            key,
            storage.objects,
        )


if __name__ == "__main__":
    unittest.main()
