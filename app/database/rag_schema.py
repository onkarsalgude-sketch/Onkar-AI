"""PostgreSQL pgvector schema management for durable RAG chunks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config.rag import RAGSettings


RAG_TABLE_NAME = "rag_chunks"

RAG_SCOPE_INDEX = (
    "idx_rag_chunks_collection_chat"
)

RAG_DOCUMENT_INDEX = (
    "idx_rag_chunks_document"
)

RAG_FILENAME_INDEX = (
    "idx_rag_chunks_filename"
)

RAG_EMBEDDING_INDEX = (
    "idx_rag_chunks_embedding_hnsw"
)


class RAGSchemaError(RuntimeError):
    """Raised without leaking database details."""

    def __init__(self):
        super().__init__(
            "RAG database schema is invalid."
        )


@dataclass(frozen=True)
class RAGSchemaReport:
    table_name: str
    collection_name: str
    embedding_dimension: int
    extension_version: str


def _require_pgvector(
    settings: RAGSettings,
) -> None:
    if not settings.is_pgvector:
        raise RAGSchemaError()

    if not settings.database.is_postgresql:
        raise RAGSchemaError()


def _schema_statements(
    embedding_dimension: int,
) -> tuple[str, ...]:
    dimension = int(
        embedding_dimension
    )

    if not 1 <= dimension <= 4096:
        raise RAGSchemaError()

    return (
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"""
        CREATE TABLE IF NOT EXISTS public.{RAG_TABLE_NAME} (
            chunk_id TEXT PRIMARY KEY,
            collection_name TEXT NOT NULL,
            chat_id INTEGER NOT NULL
                CHECK (chat_id > 0),
            document_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            page INTEGER NOT NULL
                CHECK (page > 0),
            chunk_index INTEGER NOT NULL
                CHECK (chunk_index >= 0),
            content TEXT NOT NULL
                CHECK (char_length(content) > 0),
            embedding vector({dimension}) NOT NULL,
            embedding_model TEXT NOT NULL
                DEFAULT 'default',
            created_at TEXT NOT NULL,
            UNIQUE (
                collection_name,
                chat_id,
                document_id,
                page,
                chunk_index
            )
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {RAG_SCOPE_INDEX}
        ON public.{RAG_TABLE_NAME} (
            collection_name,
            chat_id
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {RAG_DOCUMENT_INDEX}
        ON public.{RAG_TABLE_NAME} (
            collection_name,
            chat_id,
            document_id
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {RAG_FILENAME_INDEX}
        ON public.{RAG_TABLE_NAME} (
            collection_name,
            chat_id,
            lower(filename)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {RAG_EMBEDDING_INDEX}
        ON public.{RAG_TABLE_NAME}
        USING hnsw (
            embedding vector_cosine_ops
        )
        """,
    )


def _inspect_schema(
    connection,
    settings: RAGSettings,
) -> RAGSchemaReport:
    extension_version = (
        connection.execute(
            text(
                """
                SELECT extversion
                FROM pg_extension
                WHERE extname = 'vector'
                """
            )
        ).scalar_one_or_none()
    )

    if not extension_version:
        raise RAGSchemaError()

    table_reference = (
        connection.execute(
            text(
                f"""
                SELECT to_regclass(
                    'public.{RAG_TABLE_NAME}'
                )
                """
            )
        ).scalar_one_or_none()
    )

    if not table_reference:
        raise RAGSchemaError()

    embedding_type = (
        connection.execute(
            text(
                f"""
                SELECT format_type(
                    attribute.atttypid,
                    attribute.atttypmod
                )
                FROM pg_attribute AS attribute
                WHERE attribute.attrelid =
                    'public.{RAG_TABLE_NAME}'::regclass
                  AND attribute.attname =
                    'embedding'
                  AND NOT attribute.attisdropped
                """
            )
        ).scalar_one_or_none()
    )

    expected_type = (
        "vector("
        f"{settings.embedding_dimension}"
        ")"
    )

    if (
        str(embedding_type or "")
        .strip()
        .casefold()
        != expected_type.casefold()
    ):
        raise RAGSchemaError()

    return RAGSchemaReport(
        table_name=RAG_TABLE_NAME,
        collection_name=(
            settings.collection_name
        ),
        embedding_dimension=(
            settings.embedding_dimension
        ),
        extension_version=str(
            extension_version
        ),
    )


def initialize_pgvector_schema(
    engine: Engine,
    settings: RAGSettings,
) -> RAGSchemaReport:
    """Create and validate the durable RAG schema."""

    _require_pgvector(
        settings
    )

    try:
        with engine.begin() as connection:
            for statement in (
                _schema_statements(
                    settings.embedding_dimension
                )
            ):
                connection.execute(
                    text(statement)
                )

            return _inspect_schema(
                connection,
                settings,
            )

    except RAGSchemaError:
        raise

    except Exception as error:
        raise RAGSchemaError() from error


def validate_pgvector_schema(
    engine: Engine,
    settings: RAGSettings,
) -> RAGSchemaReport:
    """Validate without modifying the database."""

    _require_pgvector(
        settings
    )

    try:
        with engine.connect() as connection:
            return _inspect_schema(
                connection,
                settings,
            )

    except RAGSchemaError:
        raise

    except Exception as error:
        raise RAGSchemaError() from error
