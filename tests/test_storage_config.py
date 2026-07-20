import tempfile
import unittest
from pathlib import Path

from app.config.storage import (
    DocumentStorageConfigurationError,
    load_document_storage_settings,
)


class DocumentStorageConfigurationTests(
    unittest.TestCase
):
    def test_defaults_to_local_storage(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            settings = (
                load_document_storage_settings(
                    {},
                    default_local_root=directory,
                )
            )

        self.assertTrue(
            settings.is_local
        )
        self.assertFalse(
            settings.require_persistence
        )
        self.assertEqual(
            settings.local_root,
            Path(directory).resolve(),
        )

    def test_persistence_requirement_rejects_local(
        self,
    ):
        with self.assertRaises(
            DocumentStorageConfigurationError
        ):
            load_document_storage_settings(
                {
                    "DOCUMENT_STORAGE_BACKEND": (
                        "local"
                    ),
                    "DOCUMENT_STORAGE_REQUIRE_PERSISTENCE": (
                        "true"
                    ),
                }
            )

    def test_invalid_backend_is_rejected(
        self,
    ):
        with self.assertRaises(
            DocumentStorageConfigurationError
        ):
            load_document_storage_settings(
                {
                    "DOCUMENT_STORAGE_BACKEND": (
                        "unknown"
                    ),
                }
            )

    def test_r2_requires_complete_configuration(
        self,
    ):
        with self.assertRaises(
            DocumentStorageConfigurationError
        ):
            load_document_storage_settings(
                {
                    "DOCUMENT_STORAGE_BACKEND": (
                        "r2"
                    ),
                }
            )

    def test_valid_r2_configuration(
        self,
    ):
        settings = (
            load_document_storage_settings(
                {
                    "DOCUMENT_STORAGE_BACKEND": (
                        "r2"
                    ),
                    "DOCUMENT_STORAGE_REQUIRE_PERSISTENCE": (
                        "true"
                    ),
                    "R2_ENDPOINT_URL": (
                        "https://account.example.com/"
                    ),
                    "R2_ACCESS_KEY_ID": (
                        "access-key"
                    ),
                    "R2_SECRET_ACCESS_KEY": (
                        "secret-key"
                    ),
                    "R2_BUCKET_NAME": (
                        "onkar-ai-documents"
                    ),
                }
            )
        )

        self.assertTrue(
            settings.is_r2
        )
        self.assertEqual(
            settings.r2_endpoint_url,
            "https://account.example.com",
        )
        self.assertEqual(
            settings.safe_target,
            (
                "r2://onkar-ai-documents"
                "@account.example.com"
            ),
        )
        self.assertNotIn(
            "access-key",
            settings.safe_target,
        )
        self.assertNotIn(
            "secret-key",
            settings.safe_target,
        )

    def test_r2_endpoint_must_use_https(
        self,
    ):
        with self.assertRaises(
            DocumentStorageConfigurationError
        ):
            load_document_storage_settings(
                {
                    "DOCUMENT_STORAGE_BACKEND": (
                        "r2"
                    ),
                    "R2_ENDPOINT_URL": (
                        "http://example.com"
                    ),
                    "R2_ACCESS_KEY_ID": "key",
                    "R2_SECRET_ACCESS_KEY": (
                        "secret"
                    ),
                    "R2_BUCKET_NAME": (
                        "bucket"
                    ),
                }
            )


if __name__ == "__main__":
    unittest.main()
