"""Durable and sanitized Knowledge Library metadata operations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.config.settings import CHAT_DB
from app.database.db import (
    begin_write_transaction,
    get_runtime_connection,
)


DB_PATH = str(CHAT_DB)

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 200

ALLOWED_KNOWLEDGE_STATUSES = frozenset(
    {
        "processing",
        "ready",
        "failed",
        "deleting",
    }
)


class KnowledgeMetadataError(RuntimeError):
    """Raised when knowledge metadata cannot be handled safely."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _close_safely(value: Any) -> None:
    if value is None:
        return

    try:
        value.close()
    except Exception:
        pass


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
    maximum_length: int,
) -> str:
    candidate = str(value or "").strip()

    if (
        not candidate
        or len(candidate) > maximum_length
    ):
        raise KnowledgeMetadataError(
            f"{field_name} is invalid."
        )

    return candidate


def _normalize_knowledge_id(value: Any) -> str:
    return _normalize_required_text(
        value,
        field_name="Knowledge ID",
        maximum_length=128,
    )


def _normalize_title(value: Any) -> str:
    return _normalize_required_text(
        value,
        field_name="Knowledge title",
        maximum_length=255,
    )


def _normalize_filename(value: Any) -> str:
    candidate = _normalize_required_text(
        value,
        field_name="Knowledge filename",
        maximum_length=1024,
    )
    safe_name = Path(
        candidate.replace("\\", "/")
    ).name.strip()

    if (
        not safe_name
        or safe_name in {".", ".."}
        or len(safe_name) > 255
    ):
        raise KnowledgeMetadataError(
            "Knowledge filename is invalid."
        )

    return safe_name


def _normalize_object_key(value: Any) -> str:
    return _normalize_required_text(
        value,
        field_name="Knowledge object reference",
        maximum_length=1024,
    )


def _normalize_file_hash(value: Any) -> str:
    candidate = str(value or "").strip().casefold()

    if (
        len(candidate) != 64
        or any(
            character not in "0123456789abcdef"
            for character in candidate
        )
    ):
        raise KnowledgeMetadataError(
            "Knowledge file fingerprint is invalid."
        )

    return candidate


def _normalize_nonnegative_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise KnowledgeMetadataError(
            f"{field_name} must be a non-negative integer."
        )

    try:
        normalized = int(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        raise KnowledgeMetadataError(
            f"{field_name} must be a non-negative integer."
        ) from error

    if (
        isinstance(value, float)
        and not value.is_integer()
    ):
        raise KnowledgeMetadataError(
            f"{field_name} must be a non-negative integer."
        )

    if normalized < 0:
        raise KnowledgeMetadataError(
            f"{field_name} must be a non-negative integer."
        )

    return normalized


def _normalize_status(value: Any) -> str:
    candidate = str(value or "").strip().casefold()

    if candidate not in ALLOWED_KNOWLEDGE_STATUSES:
        raise KnowledgeMetadataError(
            "Knowledge status is invalid."
        )

    return candidate


def _normalize_enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise KnowledgeMetadataError(
            "Knowledge enabled state must be a boolean."
        )

    return value


def _normalize_limit(value: Any) -> int:
    normalized = _normalize_nonnegative_integer(
        value,
        field_name="Knowledge list limit",
    )

    if (
        normalized < 1
        or normalized > MAX_LIST_LIMIT
    ):
        raise KnowledgeMetadataError(
            "Knowledge list limit is invalid."
        )

    return normalized


def _resolve_db_path(value: str | None) -> str:
    if value is None:
        return DB_PATH

    candidate = str(value).strip()

    if not candidate:
        raise KnowledgeMetadataError(
            "Knowledge database target is invalid."
        )

    return candidate


def _record_from_row(row: Any) -> dict:
    return {
        "knowledge_id": str(row[0]),
        "title": str(row[1]),
        "filename": str(row[2]),
        "object_key": str(row[3]),
        "file_hash": str(row[4]),
        "file_size": int(row[5]),
        "page_count": int(row[6]),
        "chunk_count": int(row[7]),
        "status": str(row[8]),
        "is_enabled": bool(row[9]),
        "created_at": str(row[10]),
        "updated_at": str(row[11]),
    }


def _select_one(
    cursor: Any,
    knowledge_id: str,
) -> dict | None:
    cursor.execute(
        """
        SELECT
            knowledge_id,
            title,
            filename,
            object_key,
            file_hash,
            file_size,
            page_count,
            chunk_count,
            status,
            is_enabled,
            created_at,
            updated_at
        FROM knowledge_documents
        WHERE knowledge_id = ?
        """,
        (knowledge_id,),
    )
    row = cursor.fetchone()

    if row is None:
        return None

    return _record_from_row(row)


def get_knowledge_document(
    knowledge_id: str,
    *,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
) -> dict | None:
    """Return one internal knowledge metadata record."""

    normalized_id = _normalize_knowledge_id(
        knowledge_id
    )
    resolved_db_path = _resolve_db_path(
        db_path
    )
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        return _select_one(
            cursor,
            normalized_id,
        )
    except KnowledgeMetadataError:
        raise
    except Exception as error:
        raise KnowledgeMetadataError(
            "Knowledge metadata read failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)


def create_knowledge_document(
    title: str,
    filename: str,
    object_key: str,
    file_hash: str,
    file_size: int,
    *,
    knowledge_id: str | None = None,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
    id_factory: Callable[[], Any] = uuid4,
) -> dict:
    """Create one durable knowledge metadata record."""

    normalized_id = _normalize_knowledge_id(
        knowledge_id
        if knowledge_id is not None
        else id_factory()
    )
    normalized_title = _normalize_title(title)
    normalized_filename = _normalize_filename(
        filename
    )
    normalized_object_key = _normalize_object_key(
        object_key
    )
    normalized_hash = _normalize_file_hash(
        file_hash
    )
    normalized_size = _normalize_nonnegative_integer(
        file_size,
        field_name="Knowledge file size",
    )
    resolved_db_path = _resolve_db_path(
        db_path
    )
    now = _utc_now_iso()
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        begin_write_transaction(connection)
        cursor.execute(
            """
            INSERT INTO knowledge_documents (
                knowledge_id,
                title,
                filename,
                object_key,
                file_hash,
                file_size,
                page_count,
                chunk_count,
                status,
                is_enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'processing', 1, ?, ?)
            """,
            (
                normalized_id,
                normalized_title,
                normalized_filename,
                normalized_object_key,
                normalized_hash,
                normalized_size,
                now,
                now,
            ),
        )
        record = _select_one(
            cursor,
            normalized_id,
        )

        if record is None:
            raise KnowledgeMetadataError(
                "Knowledge metadata creation failed."
            )

        connection.commit()
        return record
    except KnowledgeMetadataError:
        if connection is not None:
            _safe_rollback(connection)
        raise
    except Exception as error:
        if connection is not None:
            _safe_rollback(connection)
        raise KnowledgeMetadataError(
            "Knowledge metadata creation failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)


def list_knowledge_documents(
    limit: int = DEFAULT_LIST_LIMIT,
    *,
    status: str | None = None,
    enabled: bool | None = None,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
) -> list[dict]:
    """Return bounded knowledge metadata newest first."""

    normalized_limit = _normalize_limit(limit)
    normalized_status = (
        _normalize_status(status)
        if status is not None
        else None
    )
    normalized_enabled = (
        _normalize_enabled(enabled)
        if enabled is not None
        else None
    )
    resolved_db_path = _resolve_db_path(
        db_path
    )
    clauses: list[str] = []
    parameters: list[Any] = []

    if normalized_status is not None:
        clauses.append("status = ?")
        parameters.append(normalized_status)

    if normalized_enabled is not None:
        clauses.append("is_enabled = ?")
        parameters.append(
            1 if normalized_enabled else 0
        )

    where_clause = (
        "WHERE " + " AND ".join(clauses)
        if clauses
        else ""
    )
    parameters.append(normalized_limit)
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT
                knowledge_id,
                title,
                filename,
                object_key,
                file_hash,
                file_size,
                page_count,
                chunk_count,
                status,
                is_enabled,
                created_at,
                updated_at
            FROM knowledge_documents
            {where_clause}
            ORDER BY
                updated_at DESC,
                knowledge_id DESC
            LIMIT ?
            """,
            tuple(parameters),
        )
        return [
            _record_from_row(row)
            for row in cursor.fetchall()
        ]
    except KnowledgeMetadataError:
        raise
    except Exception as error:
        raise KnowledgeMetadataError(
            "Knowledge metadata list failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)


def update_knowledge_document_status(
    knowledge_id: str,
    status: str,
    *,
    page_count: int | None = None,
    chunk_count: int | None = None,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
) -> dict | None:
    """Update the lifecycle status for one knowledge document."""

    normalized_id = _normalize_knowledge_id(
        knowledge_id
    )
    normalized_status = _normalize_status(status)

    if normalized_status == "ready":
        if (
            page_count is None
            or chunk_count is None
        ):
            raise KnowledgeMetadataError(
                "Ready knowledge metadata requires page and chunk counts."
            )

        normalized_page_count = (
            _normalize_nonnegative_integer(
                page_count,
                field_name="Knowledge page count",
            )
        )
        normalized_chunk_count = (
            _normalize_nonnegative_integer(
                chunk_count,
                field_name="Knowledge chunk count",
            )
        )
    else:
        if (
            page_count is not None
            or chunk_count is not None
        ):
            raise KnowledgeMetadataError(
                "Knowledge counts are only valid for ready status."
            )

        normalized_page_count = None
        normalized_chunk_count = None

    resolved_db_path = _resolve_db_path(
        db_path
    )
    now = _utc_now_iso()
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        begin_write_transaction(connection)

        if normalized_status == "ready":
            cursor.execute(
                """
                UPDATE knowledge_documents
                SET
                    status = ?,
                    page_count = ?,
                    chunk_count = ?,
                    updated_at = ?
                WHERE knowledge_id = ?
                """,
                (
                    normalized_status,
                    normalized_page_count,
                    normalized_chunk_count,
                    now,
                    normalized_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE knowledge_documents
                SET
                    status = ?,
                    updated_at = ?
                WHERE knowledge_id = ?
                """,
                (
                    normalized_status,
                    now,
                    normalized_id,
                ),
            )

        if int(cursor.rowcount) == 0:
            connection.commit()
            return None

        record = _select_one(
            cursor,
            normalized_id,
        )

        if record is None:
            raise KnowledgeMetadataError(
                "Knowledge status update failed."
            )

        connection.commit()
        return record
    except KnowledgeMetadataError:
        if connection is not None:
            _safe_rollback(connection)
        raise
    except Exception as error:
        if connection is not None:
            _safe_rollback(connection)
        raise KnowledgeMetadataError(
            "Knowledge status update failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)


def set_knowledge_document_enabled(
    knowledge_id: str,
    is_enabled: bool,
    *,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
) -> dict | None:
    """Enable or disable one knowledge document."""

    normalized_id = _normalize_knowledge_id(
        knowledge_id
    )
    normalized_enabled = _normalize_enabled(
        is_enabled
    )
    resolved_db_path = _resolve_db_path(
        db_path
    )
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        begin_write_transaction(connection)
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET
                is_enabled = ?,
                updated_at = ?
            WHERE knowledge_id = ?
            """,
            (
                1 if normalized_enabled else 0,
                _utc_now_iso(),
                normalized_id,
            ),
        )

        if int(cursor.rowcount) == 0:
            connection.commit()
            return None

        record = _select_one(
            cursor,
            normalized_id,
        )

        if record is None:
            raise KnowledgeMetadataError(
                "Knowledge enabled-state update failed."
            )

        connection.commit()
        return record
    except KnowledgeMetadataError:
        if connection is not None:
            _safe_rollback(connection)
        raise
    except Exception as error:
        if connection is not None:
            _safe_rollback(connection)
        raise KnowledgeMetadataError(
            "Knowledge enabled-state update failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)


def delete_knowledge_document(
    knowledge_id: str,
    *,
    db_path: str | None = None,
    connection_factory: Callable = get_runtime_connection,
) -> bool:
    """Delete one knowledge metadata record idempotently."""

    normalized_id = _normalize_knowledge_id(
        knowledge_id
    )
    resolved_db_path = _resolve_db_path(
        db_path
    )
    connection = None
    cursor = None

    try:
        connection = connection_factory(
            resolved_db_path
        )
        cursor = connection.cursor()
        begin_write_transaction(connection)
        cursor.execute(
            """
            DELETE FROM knowledge_documents
            WHERE knowledge_id = ?
            """,
            (normalized_id,),
        )
        deleted = int(cursor.rowcount) > 0
        connection.commit()
        return deleted
    except KnowledgeMetadataError:
        if connection is not None:
            _safe_rollback(connection)
        raise
    except Exception as error:
        if connection is not None:
            _safe_rollback(connection)
        raise KnowledgeMetadataError(
            "Knowledge metadata deletion failed."
        ) from error
    finally:
        _close_safely(cursor)
        _close_safely(connection)
