import unittest

from app.database.rag_schema import (
    RAGSchemaReport,
)
from app.services.rag_runtime import (
    RAGRuntimeError,
    initialize_rag_runtime,
)


POSTGRES_URL = (
    "postgresql://"
    "user:secret@"
    "db.example.com:5432/onkar"
)


class FakeEngine:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


class RAGRuntimeTests(
    unittest.TestCase
):
    def test_local_runtime_uses_chroma_without_database_engine(
        self,
    ):
        builder_calls = []

        runtime = (
            initialize_rag_runtime(
                {},
                engine_builder=(
                    lambda settings:
                    builder_calls.append(
                        settings
                    )
                ),
            )
        )

        self.assertTrue(
            runtime.settings.is_chroma
        )

        self.assertIsNone(
            runtime.schema_report
        )

        self.assertEqual(
            builder_calls,
            [],
        )

    def test_pgvector_runtime_initializes_schema(
        self,
    ):
        engine = FakeEngine()
        received = {}

        def initialize(
            supplied_engine,
            settings,
        ):
            received["engine"] = (
                supplied_engine
            )

            received["settings"] = (
                settings
            )

            return RAGSchemaReport(
                table_name="rag_chunks",
                collection_name=(
                    settings
                    .collection_name
                ),
                embedding_dimension=(
                    settings
                    .embedding_dimension
                ),
                extension_version=(
                    "0.8.0"
                ),
            )

        runtime = (
            initialize_rag_runtime(
                {
                    "DATABASE_URL": (
                        POSTGRES_URL
                    ),
                    "RAG_BACKEND": (
                        "pgvector"
                    ),
                },
                engine_builder=(
                    lambda settings: engine
                ),
                schema_initializer=(
                    initialize
                ),
            )
        )

        self.assertTrue(
            runtime.settings.is_pgvector
        )

        self.assertEqual(
            runtime.schema_report
            .table_name,
            "rag_chunks",
        )

        self.assertIs(
            received["engine"],
            engine,
        )

        self.assertTrue(
            engine.disposed
        )

    def test_schema_failure_is_sanitized_and_engine_is_disposed(
        self,
    ):
        engine = FakeEngine()

        def fail(
            supplied_engine,
            settings,
        ):
            del supplied_engine
            del settings

            raise RuntimeError(
                "postgresql://"
                "user:private-secret@host/db"
            )

        with self.assertRaises(
            RAGRuntimeError
        ) as context:
            initialize_rag_runtime(
                {
                    "DATABASE_URL": (
                        POSTGRES_URL
                    ),
                },
                engine_builder=(
                    lambda settings: engine
                ),
                schema_initializer=(
                    fail
                ),
            )

        self.assertEqual(
            str(context.exception),
            (
                "RAG persistence "
                "initialization failed."
            ),
        )

        self.assertNotIn(
            "private-secret",
            str(context.exception),
        )

        self.assertTrue(
            engine.disposed
        )

    def test_invalid_configuration_is_sanitized(
        self,
    ):
        with self.assertRaises(
            RAGRuntimeError
        ):
            initialize_rag_runtime(
                {
                    "RAG_BACKEND": (
                        "pgvector"
                    ),
                }
            )


if __name__ == "__main__":
    unittest.main()
