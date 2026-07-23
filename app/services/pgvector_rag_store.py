"""Transactional PostgreSQL pgvector storage for durable RAG chunks."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.rag import RAGSettings
from app.database.db import get_runtime_connection
from app.database.rag_schema import RAG_TABLE_NAME


MAX_SEARCH_LIMIT = 20
MAX_TEXT_LENGTH = 100_000


class PgVectorRAGStoreError(RuntimeError):
    """Raised without exposing database data or credentials."""

    def __init__(self):
        super().__init__(
            "Pgvector RAG storage operation failed."
        )


@dataclass(frozen=True)
class PgVectorChunk:
    chunk_id: str
    chat_id: int
    document_id: str
    filename: str
    page: int
    chunk_index: int
    content: str
    embedding: Sequence[float]


def _required_text(
    value: object,
    *,
    maximum_length: int,
) -> str:
    candidate = str(
        value or ""
    ).strip()

    if (
        not candidate
        or len(candidate) > maximum_length
        or any(
            ord(character) < 32
            and character not in {
                "\n",
                "\r",
                "\t",
            }
            for character in candidate
        )
    ):
        raise PgVectorRAGStoreError()

    return candidate


def _safe_filename(
    value: object,
) -> str:
    candidate = _required_text(
        value,
        maximum_length=255,
    )

    if (
        "/" in candidate
        or "\\" in candidate
        or Path(candidate).name
        != candidate
        or Path(candidate).suffix.casefold()
        != ".pdf"
    ):
        raise PgVectorRAGStoreError()

    return candidate


def _positive_integer(
    value: object,
) -> int:
    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            PgVectorRAGStoreError()
        ) from error

    if parsed <= 0:
        raise PgVectorRAGStoreError()

    return parsed


def _non_negative_integer(
    value: object,
) -> int:
    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            PgVectorRAGStoreError()
        ) from error

    if parsed < 0:
        raise PgVectorRAGStoreError()

    return parsed


def _vector_literal(
    values: Sequence[float],
    *,
    dimension: int,
) -> str:
    if isinstance(
        values,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        raise PgVectorRAGStoreError()

    try:
        vector = [
            float(value)
            for value in values
        ]
    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        raise (
            PgVectorRAGStoreError()
        ) from error

    if len(vector) != dimension:
        raise PgVectorRAGStoreError()

    if not all(
        math.isfinite(value)
        for value in vector
    ):
        raise PgVectorRAGStoreError()

    return (
        "["
        + ",".join(
            format(value, ".17g")
            for value in vector
        )
        + "]"
    )


def _close_safely(
    resource,
) -> None:
    close = getattr(
        resource,
        "close",
        None,
    )

    if callable(close):
        close()


class PgVectorRAGStore:
    """Store and search RAG chunks in PostgreSQL pgvector."""

    def __init__(
        self,
        settings: RAGSettings,
        *,
        connection_factory:
        Callable[[], Any] | None = None,
    ):
        if (
            not settings.is_pgvector
            or not settings.database
            .is_postgresql
        ):
            raise PgVectorRAGStoreError()

        self.settings = settings

        if connection_factory is None:
            environment = {
                "DATABASE_URL": (
                    settings.database
                    .database_url
                    or ""
                ),
                "DATABASE_POOL_SIZE": str(
                    settings.database.pool_size
                ),
                "DATABASE_CONNECT_TIMEOUT": str(
                    settings.database
                    .connect_timeout_seconds
                ),
                "DATABASE_REQUIRE_PERSISTENCE": (
                    "true"
                    if settings.database
                    .require_persistence
                    else "false"
                ),
            }

            self._connection_factory = (
                lambda: get_runtime_connection(
                    environ=environment
                )
            )

        else:
            self._connection_factory = (
                connection_factory
            )

    def _normalize_chunk(
        self,
        chunk: PgVectorChunk,
    ) -> tuple[
        str,
        int,
        str,
        str,
        int,
        int,
        str,
        str,
    ]:
        return (
            _required_text(
                chunk.chunk_id,
                maximum_length=512,
            ),
            _positive_integer(
                chunk.chat_id
            ),
            _required_text(
                chunk.document_id,
                maximum_length=255,
            ),
            _safe_filename(
                chunk.filename
            ),
            _positive_integer(
                chunk.page
            ),
            _non_negative_integer(
                chunk.chunk_index
            ),
            _required_text(
                chunk.content,
                maximum_length=(
                    MAX_TEXT_LENGTH
                ),
            ),
            _vector_literal(
                chunk.embedding,
                dimension=(
                    self.settings
                    .embedding_dimension
                ),
            ),
        )

    def replace_document_chunks(
        self,
        chunks: Iterable[
            PgVectorChunk
        ],
        *,
        chat_id: int,
        document_id: str,
    ) -> int:
        """Atomically replace all chunks for one document."""

        resolved_chat_id = (
            _positive_integer(
                chat_id
            )
        )

        resolved_document_id = (
            _required_text(
                document_id,
                maximum_length=255,
            )
        )

        normalized_chunks = [
            self._normalize_chunk(
                chunk
            )
            for chunk in chunks
        ]

        for normalized in (
            normalized_chunks
        ):
            if (
                normalized[1]
                != resolved_chat_id
                or normalized[2]
                != resolved_document_id
            ):
                raise (
                    PgVectorRAGStoreError()
                )

        connection = (
            self._connection_factory()
        )

        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                DELETE FROM public.{RAG_TABLE_NAME}
                WHERE collection_name = ?
                  AND chat_id = ?
                  AND document_id = ?
                """,
                (
                    self.settings
                    .collection_name,
                    resolved_chat_id,
                    resolved_document_id,
                ),
            )

            created_at = datetime.now(
                timezone.utc
            ).isoformat()

            for (
                chunk_id,
                normalized_chat_id,
                normalized_document_id,
                filename,
                page,
                chunk_index,
                content,
                embedding,
            ) in normalized_chunks:
                cursor.execute(
                    f"""
                    INSERT INTO public.{RAG_TABLE_NAME} (
                        chunk_id,
                        collection_name,
                        chat_id,
                        document_id,
                        filename,
                        page,
                        chunk_index,
                        content,
                        embedding,
                        embedding_model,
                        created_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, CAST(? AS vector),
                        'default', ?
                    )
                    """,
                    (
                        chunk_id,
                        self.settings
                        .collection_name,
                        normalized_chat_id,
                        normalized_document_id,
                        filename,
                        page,
                        chunk_index,
                        content,
                        embedding,
                        created_at,
                    ),
                )

            connection.commit()

            return len(
                normalized_chunks
            )

        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass

            raise (
                PgVectorRAGStoreError()
            ) from error

        finally:
            _close_safely(cursor)
            _close_safely(connection)

    @staticmethod
    def _normalize_document_ids(
        document_ids:
        Sequence[str] | None,
    ) -> list[str] | None:
        if document_ids is None:
            return None

        if isinstance(
            document_ids,
            (str, bytes),
        ):
            raise PgVectorRAGStoreError()

        selected: list[str] = []
        seen: set[str] = set()

        for value in document_ids:
            candidate = str(
                value or ""
            ).strip()

            if (
                not candidate
                or len(candidate) > 128
            ):
                raise PgVectorRAGStoreError()

            if candidate in seen:
                continue

            seen.add(candidate)
            selected.append(candidate)

            if len(selected) > 200:
                raise PgVectorRAGStoreError()

        return selected

    def search(
        self,
        query_embedding:
        Sequence[float],
        *,
        chat_id: int,
        limit: int = 5,
        filename: str | None = None,
        filenames:
        Sequence[str] | None = None,
        document_ids:
        Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        resolved_chat_id = (
            _positive_integer(
                chat_id
            )
        )

        try:
            resolved_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise (
                PgVectorRAGStoreError()
            ) from error

        if not (
            1
            <= resolved_limit
            <= MAX_SEARCH_LIMIT
        ):
            raise PgVectorRAGStoreError()

        selected_document_ids = (
            self._normalize_document_ids(
                document_ids
            )
        )

        if (
            document_ids is not None
            and not selected_document_ids
        ):
            return []

        query_vector = _vector_literal(
            query_embedding,
            dimension=(
                self.settings
                .embedding_dimension
            ),
        )

        selected_filenames: list[str] = []

        if filename:
            selected_filenames = [
                _safe_filename(
                    filename
                )
            ]

        elif filenames is not None:
            selected_filenames = list(
                dict.fromkeys(
                    _safe_filename(item)
                    for item in filenames
                    if str(item or "").strip()
                )
            )

            if not selected_filenames:
                return []

        filters = [
            "collection_name = ?",
            "chat_id = ?",
        ]

        filter_parameters: list[
            object
        ] = [
            self.settings.collection_name,
            resolved_chat_id,
        ]

        if selected_filenames:
            placeholders = ", ".join(
                "?"
                for _ in selected_filenames
            )
            filters.append(
                "lower(filename) IN ("
                + placeholders
                + ")"
            )
            filter_parameters.extend(
                item.casefold()
                for item
                in selected_filenames
            )

        if selected_document_ids:
            placeholders = ", ".join(
                "?"
                for _ in selected_document_ids
            )
            filters.append(
                "document_id IN ("
                + placeholders
                + ")"
            )
            filter_parameters.extend(
                selected_document_ids
            )

        where_clause = " AND ".join(
            filters
        )

        sql = f"""
            SELECT
                content,
                filename,
                page,
                document_id,
                chunk_index,
                (
                    embedding
                    <=> CAST(? AS vector)
                ) AS distance
            FROM public.{RAG_TABLE_NAME}
            WHERE {where_clause}
            ORDER BY
                embedding
                <=> CAST(? AS vector),
                page,
                chunk_index
            LIMIT ?
        """

        parameters = (
            query_vector,
            *filter_parameters,
            query_vector,
            resolved_limit,
        )

        connection = (
            self._connection_factory()
        )
        cursor = connection.cursor()

        try:
            cursor.execute(
                sql,
                parameters,
            )
            rows = cursor.fetchall()

            return [
                {
                    "content": row[0],
                    "filename": row[1],
                    "page": int(row[2]),
                    "document_id": row[3],
                    "chunk_index": int(
                        row[4]
                    ),
                    "distance": float(
                        row[5]
                    ),
                }
                for row in rows
            ]

        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass

            raise (
                PgVectorRAGStoreError()
            ) from error

        finally:
            _close_safely(cursor)
            _close_safely(connection)

    def delete_document(
        self,
        *,
        chat_id: int,
        document_id: str,
    ) -> int:
        return self._delete(
            """
            collection_name = ?
            AND chat_id = ?
            AND document_id = ?
            """,
            (
                self.settings.collection_name,
                _positive_integer(
                    chat_id
                ),
                _required_text(
                    document_id,
                    maximum_length=255,
                ),
            ),
        )

    def delete_filename(
        self,
        *,
        chat_id: int,
        filename: str,
    ) -> int:
        return self._delete(
            """
            collection_name = ?
            AND chat_id = ?
            AND lower(filename) = ?
            """,
            (
                self.settings.collection_name,
                _positive_integer(
                    chat_id
                ),
                _safe_filename(
                    filename
                ).casefold(),
            ),
        )

    def delete_chat(
        self,
        *,
        chat_id: int,
    ) -> int:
        return self._delete(
            """
            collection_name = ?
            AND chat_id = ?
            """,
            (
                self.settings.collection_name,
                _positive_integer(
                    chat_id
                ),
            ),
        )

    def _delete(
        self,
        where_clause: str,
        parameters: tuple[
            object,
            ...,
        ],
    ) -> int:
        connection = (
            self._connection_factory()
        )

        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                DELETE FROM public.{RAG_TABLE_NAME}
                WHERE {where_clause}
                """,
                parameters,
            )

            deleted_count = max(
                int(cursor.rowcount),
                0,
            )

            connection.commit()

            return deleted_count

        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass

            raise (
                PgVectorRAGStoreError()
            ) from error

        finally:
            _close_safely(cursor)
            _close_safely(connection)

    def count(
        self,
        *,
        chat_id: int,
    ) -> int:
        connection = (
            self._connection_factory()
        )

        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM public.{RAG_TABLE_NAME}
                WHERE collection_name = ?
                  AND chat_id = ?
                """,
                (
                    self.settings
                    .collection_name,
                    _positive_integer(
                        chat_id
                    ),
                ),
            )

            row = cursor.fetchone()

            return (
                int(row[0])
                if row is not None
                else 0
            )

        except Exception as error:
            try:
                connection.rollback()
            except Exception:
                pass

            raise (
                PgVectorRAGStoreError()
            ) from error

        finally:
            _close_safely(cursor)
            _close_safely(connection)
