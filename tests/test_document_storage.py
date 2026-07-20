import io
import tempfile
import unittest
from pathlib import Path

from app.config.storage import (
    DocumentStorageSettings,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    LocalDocumentStorage,
    R2DocumentStorage,
    build_document_storage,
    normalize_object_key,
)


class FakeS3Error(Exception):
    def __init__(
        self,
        code="NoSuchKey",
    ):
        self.response = {
            "Error": {
                "Code": code,
            }
        }
        super().__init__(code)


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.content_types = {}

    def put_object(
        self,
        *,
        Bucket,
        Key,
        Body,
        ContentType,
    ):
        storage_key = (
            Bucket,
            Key,
        )
        self.objects[
            storage_key
        ] = bytes(Body)
        self.content_types[
            storage_key
        ] = ContentType

    def get_object(
        self,
        *,
        Bucket,
        Key,
    ):
        storage_key = (
            Bucket,
            Key,
        )

        if storage_key not in self.objects:
            raise FakeS3Error()

        return {
            "Body": io.BytesIO(
                self.objects[storage_key]
            )
        }

    def head_object(
        self,
        *,
        Bucket,
        Key,
    ):
        if (
            Bucket,
            Key,
        ) not in self.objects:
            raise FakeS3Error()

        return {}

    def delete_object(
        self,
        *,
        Bucket,
        Key,
    ):
        self.objects.pop(
            (
                Bucket,
                Key,
            ),
            None,
        )


def r2_settings():
    return DocumentStorageSettings(
        backend="r2",
        require_persistence=True,
        local_root=Path(
            "unused"
        ),
        r2_endpoint_url=(
            "https://example.r2.test"
        ),
        r2_access_key_id="access",
        r2_secret_access_key="secret",
        r2_bucket_name="documents",
        r2_region="auto",
    )


class LocalDocumentStorageTests(
    unittest.TestCase
):
    def test_round_trip_and_delete(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = (
                LocalDocumentStorage(
                    directory
                )
            )

            key = (
                "chats/12/documents/"
                "report.pdf"
            )

            self.assertEqual(
                storage.put_bytes(
                    key,
                    b"%PDF-test",
                    content_type=(
                        "application/pdf"
                    ),
                ),
                key,
            )

            self.assertTrue(
                storage.exists(key)
            )
            self.assertEqual(
                storage.get_bytes(key),
                b"%PDF-test",
            )
            self.assertTrue(
                storage.delete(key)
            )
            self.assertFalse(
                storage.exists(key)
            )
            self.assertFalse(
                storage.delete(key)
            )

    def test_missing_object_raises(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            storage = (
                LocalDocumentStorage(
                    directory
                )
            )

            with self.assertRaises(
                DocumentNotFoundError
            ):
                storage.get_bytes(
                    "missing/file.pdf"
                )

    def test_factory_builds_local_backend(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            settings = (
                DocumentStorageSettings(
                    backend="local",
                    require_persistence=False,
                    local_root=Path(
                        directory
                    ),
                    r2_endpoint_url="",
                    r2_access_key_id="",
                    r2_secret_access_key="",
                    r2_bucket_name="",
                    r2_region="auto",
                )
            )

            storage = (
                build_document_storage(
                    settings
                )
            )

            self.assertIsInstance(
                storage,
                LocalDocumentStorage,
            )


class R2DocumentStorageTests(
    unittest.TestCase
):
    def test_round_trip_and_delete(
        self,
    ):
        client = FakeS3Client()
        storage = R2DocumentStorage(
            r2_settings(),
            client=client,
        )

        key = (
            "chats/22/documents/"
            "notes.pdf"
        )

        storage.put_bytes(
            key,
            b"%PDF-r2",
            content_type=(
                "application/pdf"
            ),
        )

        self.assertTrue(
            storage.exists(key)
        )
        self.assertEqual(
            storage.get_bytes(key),
            b"%PDF-r2",
        )
        self.assertEqual(
            client.content_types[
                (
                    "documents",
                    key,
                )
            ],
            "application/pdf",
        )
        self.assertTrue(
            storage.delete(key)
        )
        self.assertFalse(
            storage.exists(key)
        )

    def test_missing_object_raises(
        self,
    ):
        storage = R2DocumentStorage(
            r2_settings(),
            client=FakeS3Client(),
        )

        with self.assertRaises(
            DocumentNotFoundError
        ):
            storage.get_bytes(
                "missing/file.pdf"
            )

    def test_factory_builds_r2_backend(
        self,
    ):
        storage = (
            build_document_storage(
                r2_settings(),
                r2_client=FakeS3Client(),
            )
        )

        self.assertIsInstance(
            storage,
            R2DocumentStorage,
        )


class ObjectKeyValidationTests(
    unittest.TestCase
):
    def test_valid_key_is_preserved(
        self,
    ):
        self.assertEqual(
            normalize_object_key(
                "chats/1/file.pdf"
            ),
            "chats/1/file.pdf",
        )

    def test_unsafe_keys_are_rejected(
        self,
    ):
        unsafe_keys = (
            "",
            "/absolute.pdf",
            "../secret.pdf",
            "chat/../secret.pdf",
            "chat\\secret.pdf",
            "chat/",
        )

        for key in unsafe_keys:
            with self.subTest(
                key=key
            ):
                with self.assertRaises(
                    ValueError
                ):
                    normalize_object_key(
                        key
                    )


if __name__ == "__main__":
    unittest.main()
