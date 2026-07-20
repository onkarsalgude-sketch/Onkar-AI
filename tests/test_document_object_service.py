import tempfile
import unittest
from pathlib import Path

from app.services.document_object_service import (
    build_document_object_key,
    delete_document_object,
    materialize_pdf_bytes,
    read_document_bytes,
    store_document_bytes,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    LocalDocumentStorage,
)


class DocumentObjectServiceTests(
    unittest.TestCase
):
    def test_object_round_trip(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalDocumentStorage(
                directory
            )

            file_hash = "a" * 64

            key = store_document_bytes(
                chat_id=12,
                document_id="document-1",
                filename="report.pdf",
                file_hash=file_hash,
                data=b"%PDF-test",
                storage=storage,
            )

            self.assertEqual(
                key,
                (
                    "chats/12/documents/"
                    "document-1/"
                    f"{file_hash}/"
                    "report.pdf"
                ),
            )

            document = {
                "chat_id": 12,
                "document_id": (
                    "document-1"
                ),
                "filename": "report.pdf",
                "file_path": key,
            }

            self.assertEqual(
                read_document_bytes(
                    document,
                    storage=storage,
                ),
                b"%PDF-test",
            )

            self.assertTrue(
                delete_document_object(
                    document,
                    storage=storage,
                )
            )

            with self.assertRaises(
                DocumentNotFoundError
            ):
                read_document_bytes(
                    document,
                    storage=storage,
                )

    def test_legacy_local_path_is_supported(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalDocumentStorage(
                directory
            )

            legacy_directory = (
                Path(directory)
                / "chat_7"
            )

            legacy_directory.mkdir(
                parents=True
            )

            legacy_file = (
                legacy_directory
                / "legacy.pdf"
            )

            legacy_file.write_bytes(
                b"%PDF-legacy"
            )

            document = {
                "chat_id": 7,
                "document_id": "legacy-1",
                "filename": "legacy.pdf",
                "file_path": str(
                    legacy_file
                ),
            }

            self.assertEqual(
                read_document_bytes(
                    document,
                    storage=storage,
                ),
                b"%PDF-legacy",
            )

            self.assertTrue(
                delete_document_object(
                    document,
                    storage=storage,
                )
            )

            self.assertFalse(
                legacy_file.exists()
            )

    def test_temporary_pdf_is_removed(
        self,
    ):
        with materialize_pdf_bytes(
            b"%PDF-temporary",
            "temporary.pdf",
        ) as temporary_path:
            self.assertTrue(
                temporary_path.is_file()
            )

            self.assertEqual(
                temporary_path.read_bytes(),
                b"%PDF-temporary",
            )

        self.assertFalse(
            temporary_path.exists()
        )

    def test_invalid_object_inputs_are_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            build_document_object_key(
                chat_id=0,
                document_id="document",
                filename="report.pdf",
                file_hash="a" * 64,
            )

        with self.assertRaises(
            ValueError
        ):
            build_document_object_key(
                chat_id=1,
                document_id="../document",
                filename="report.pdf",
                file_hash="a" * 64,
            )

        with self.assertRaises(
            ValueError
        ):
            build_document_object_key(
                chat_id=1,
                document_id="document",
                filename="../report.pdf",
                file_hash="a" * 64,
            )

        with self.assertRaises(
            ValueError
        ):
            build_document_object_key(
                chat_id=1,
                document_id="document",
                filename="report.pdf",
                file_hash="invalid",
            )


if __name__ == "__main__":
    unittest.main()
