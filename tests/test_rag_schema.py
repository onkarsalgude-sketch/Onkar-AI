import unittest

from app.config.rag import (
    load_rag_settings,
)
from app.database.rag_schema import (
    RAG_DOCUMENT_INDEX,
    RAG_EMBEDDING_INDEX,
    RAG_FILENAME_INDEX,
    RAG_SCOPE_INDEX,
    RAGSchemaError,
    initialize_pgvector_schema,
    validate_pgvector_schema,
)


POSTGRES_URL = (
    "postgresql://"
    "user:secret@"
    "db.example.com:5432/onkar"
)


class FakeResult:
    def __init__(
        self,
        value,
    ):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeConnection:
    def __init__(
        self,
        *,
        dimension=384,
        extension_version="0.8.0",
        table_reference="rag_chunks",
        failure=None,
    ):
        self.dimension = dimension
        self.extension_version = (
            extension_version
        )
        self.table_reference = (
            table_reference
        )
        self.failure = failure
        self.statements = []

    def execute(
        self,
        statement,
        parameters=None,
    ):
        del parameters

        sql = str(statement)

        self.statements.append(
            sql
        )

        if self.failure is not None:
            raise self.failure

        normalized = " ".join(
            sql.split()
        ).casefold()

        if "from pg_extension" in normalized:
            return FakeResult(
                self.extension_version
            )

        if "to_regclass" in normalized:
            return FakeResult(
                self.table_reference
            )

        if "format_type" in normalized:
            return FakeResult(
                f"vector({self.dimension})"
            )

        return FakeResult(None)


class FakeContext:
    def __init__(
        self,
        connection,
    ):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(
        self,
        exception_type,
        exception,
        traceback,
    ):
        del exception_type
        del exception
        del traceback

        return False


class FakeEngine:
    def __init__(
        self,
        connection=None,
    ):
        self.connection = (
            connection
            or FakeConnection()
        )
        self.begin_calls = 0
        self.connect_calls = 0

    def begin(self):
        self.begin_calls += 1

        return FakeContext(
            self.connection
        )

    def connect(self):
        self.connect_calls += 1

        return FakeContext(
            self.connection
        )


def pgvector_settings(
    *,
    dimension=384,
):
    return load_rag_settings(
        {
            "DATABASE_URL": (
                POSTGRES_URL
            ),
            "RAG_BACKEND": (
                "pgvector"
            ),
            "RAG_EMBEDDING_DIMENSION": (
                str(dimension)
            ),
        }
    )


class RAGSchemaTests(
    unittest.TestCase
):
    def test_chroma_backend_is_rejected(
        self,
    ):
        settings = load_rag_settings(
            {}
        )

        with self.assertRaises(
            RAGSchemaError
        ):
            initialize_pgvector_schema(
                FakeEngine(),
                settings,
            )

    def test_initialization_creates_extension_table_and_indexes(
        self,
    ):
        engine = FakeEngine()

        report = initialize_pgvector_schema(
            engine,
            pgvector_settings(),
        )

        ddl = "\n".join(
            engine.connection.statements
        ).casefold()

        self.assertIn(
            "create extension if not exists vector",
            ddl,
        )

        self.assertIn(
            "create table if not exists public.rag_chunks",
            " ".join(ddl.split()),
        )

        self.assertIn(
            "embedding vector(384) not null",
            " ".join(ddl.split()),
        )

        for index_name in (
            RAG_SCOPE_INDEX,
            RAG_DOCUMENT_INDEX,
            RAG_FILENAME_INDEX,
            RAG_EMBEDDING_INDEX,
        ):
            self.assertIn(
                index_name.casefold(),
                ddl,
            )

        self.assertIn(
            "using hnsw",
            ddl,
        )

        self.assertIn(
            "vector_cosine_ops",
            ddl,
        )

        self.assertEqual(
            report.table_name,
            "rag_chunks",
        )

        self.assertEqual(
            report.embedding_dimension,
            384,
        )

        self.assertEqual(
            report.extension_version,
            "0.8.0",
        )

    def test_custom_dimension_is_used_in_table_and_validation(
        self,
    ):
        connection = FakeConnection(
            dimension=768
        )

        engine = FakeEngine(
            connection
        )

        report = initialize_pgvector_schema(
            engine,
            pgvector_settings(
                dimension=768
            ),
        )

        ddl = "\n".join(
            connection.statements
        ).casefold()

        self.assertIn(
            "vector(768)",
            ddl,
        )

        self.assertEqual(
            report.embedding_dimension,
            768,
        )

    def test_repeated_initialization_is_idempotent(
        self,
    ):
        engine = FakeEngine()
        settings = pgvector_settings()

        first = initialize_pgvector_schema(
            engine,
            settings,
        )

        second = initialize_pgvector_schema(
            engine,
            settings,
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            engine.begin_calls,
            2,
        )

    def test_validation_is_read_only(
        self,
    ):
        engine = FakeEngine()

        report = validate_pgvector_schema(
            engine,
            pgvector_settings(),
        )

        ddl = "\n".join(
            engine.connection.statements
        ).casefold()

        self.assertNotIn(
            "create extension",
            ddl,
        )

        self.assertNotIn(
            "create table",
            ddl,
        )

        self.assertEqual(
            engine.begin_calls,
            0,
        )

        self.assertEqual(
            engine.connect_calls,
            1,
        )

        self.assertEqual(
            report.table_name,
            "rag_chunks",
        )

    def test_dimension_mismatch_fails_closed(
        self,
    ):
        engine = FakeEngine(
            FakeConnection(
                dimension=768
            )
        )

        with self.assertRaises(
            RAGSchemaError
        ):
            validate_pgvector_schema(
                engine,
                pgvector_settings(
                    dimension=384
                ),
            )

    def test_missing_extension_fails_closed(
        self,
    ):
        engine = FakeEngine(
            FakeConnection(
                extension_version=None
            )
        )

        with self.assertRaises(
            RAGSchemaError
        ):
            validate_pgvector_schema(
                engine,
                pgvector_settings(),
            )

    def test_database_errors_are_sanitized(
        self,
    ):
        secret_error = RuntimeError(
            "postgresql://"
            "user:very-secret@host/db"
        )

        engine = FakeEngine(
            FakeConnection(
                failure=secret_error
            )
        )

        with self.assertRaises(
            RAGSchemaError
        ) as context:
            initialize_pgvector_schema(
                engine,
                pgvector_settings(),
            )

        message = str(
            context.exception
        )

        self.assertEqual(
            message,
            "RAG database schema is invalid.",
        )

        self.assertNotIn(
            "very-secret",
            message,
        )


if __name__ == "__main__":
    unittest.main()
