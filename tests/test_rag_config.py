import tempfile
import unittest
from pathlib import Path

from app.config.rag import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_DIMENSION,
    RAGConfigurationError,
    load_rag_settings,
)


POSTGRES_URL = (
    "postgresql://"
    "user:super-secret@"
    "db.example.com:5432/onkar"
)


class RAGConfigurationTests(
    unittest.TestCase
):
    def test_defaults_to_chroma_for_sqlite(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            vector_path = (
                Path(directory)
                / "vectors"
            )

            settings = (
                load_rag_settings(
                    {},
                    default_chroma_path=(
                        vector_path
                    ),
                )
            )

        self.assertTrue(
            settings.is_chroma
        )

        self.assertFalse(
            settings.is_pgvector
        )

        self.assertFalse(
            settings.require_persistence
        )

        self.assertEqual(
            settings.embedding_dimension,
            DEFAULT_EMBEDDING_DIMENSION,
        )

        self.assertEqual(
            settings.collection_name,
            DEFAULT_COLLECTION_NAME,
        )

        self.assertEqual(
            settings.chroma_path,
            vector_path,
        )

    def test_postgresql_defaults_to_pgvector(
        self,
    ):
        settings = load_rag_settings(
            {
                "DATABASE_URL": (
                    POSTGRES_URL
                ),
            }
        )

        self.assertTrue(
            settings.is_pgvector
        )

        self.assertFalse(
            settings.require_persistence
        )

    def test_explicit_chroma_can_be_used_with_postgresql_for_development(
        self,
    ):
        settings = load_rag_settings(
            {
                "DATABASE_URL": (
                    POSTGRES_URL
                ),
                "RAG_BACKEND": (
                    "chroma"
                ),
            }
        )

        self.assertTrue(
            settings.is_chroma
        )

    def test_pgvector_requires_postgresql(
        self,
    ):
        with self.assertRaises(
            RAGConfigurationError
        ):
            load_rag_settings(
                {
                    "RAG_BACKEND": (
                        "pgvector"
                    ),
                }
            )

    def test_database_persistence_forces_pgvector_persistence(
        self,
    ):
        settings = load_rag_settings(
            {
                "DATABASE_URL": (
                    POSTGRES_URL
                ),
                "DATABASE_REQUIRE_PERSISTENCE": (
                    "true"
                ),
            }
        )

        self.assertTrue(
            settings.is_pgvector
        )

        self.assertTrue(
            settings.require_persistence
        )

    def test_persistent_database_rejects_chroma(
        self,
    ):
        with self.assertRaises(
            RAGConfigurationError
        ):
            load_rag_settings(
                {
                    "DATABASE_URL": (
                        POSTGRES_URL
                    ),
                    "DATABASE_REQUIRE_PERSISTENCE": (
                        "true"
                    ),
                    "RAG_BACKEND": (
                        "chroma"
                    ),
                }
            )

    def test_rag_persistence_rejects_local_chroma(
        self,
    ):
        with self.assertRaises(
            RAGConfigurationError
        ):
            load_rag_settings(
                {
                    "RAG_BACKEND": (
                        "chroma"
                    ),
                    "RAG_REQUIRE_PERSISTENCE": (
                        "true"
                    ),
                }
            )

    def test_invalid_values_fail_closed(
        self,
    ):
        invalid_environments = (
            {
                "RAG_BACKEND": (
                    "redis"
                ),
            },
            {
                "RAG_REQUIRE_PERSISTENCE": (
                    "maybe"
                ),
            },
            {
                "RAG_EMBEDDING_DIMENSION": (
                    "0"
                ),
            },
            {
                "RAG_EMBEDDING_DIMENSION": (
                    "4097"
                ),
            },
            {
                "RAG_EMBEDDING_DIMENSION": (
                    "not-a-number"
                ),
            },
            {
                "RAG_COLLECTION_NAME": (
                    "-invalid"
                ),
            },
        )

        for environment in (
            invalid_environments
        ):
            with self.subTest(
                environment=environment
            ):
                with self.assertRaises(
                    RAGConfigurationError
                ):
                    load_rag_settings(
                        environment
                    )

    def test_vector_directory_can_be_configured(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            configured_path = (
                Path(directory)
                / "custom-vectors"
            )

            settings = (
                load_rag_settings(
                    {
                        "VECTOR_DB_DIR": str(
                            configured_path
                        ),
                    }
                )
            )

        self.assertEqual(
            settings.chroma_path,
            configured_path,
        )

    def test_safe_target_never_exposes_database_credentials(
        self,
    ):
        settings = load_rag_settings(
            {
                "DATABASE_URL": (
                    POSTGRES_URL
                ),
            }
        )

        safe_target = (
            settings.safe_target
        )

        self.assertIn(
            "db.example.com",
            safe_target,
        )

        self.assertNotIn(
            "super-secret",
            safe_target,
        )

        self.assertNotIn(
            "user:",
            safe_target,
        )


if __name__ == "__main__":
    unittest.main()
