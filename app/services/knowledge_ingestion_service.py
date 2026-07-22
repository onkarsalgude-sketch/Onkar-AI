"""Backend-only orchestration for durable Knowledge PDF ingestion."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.document_object_service import (
    materialize_pdf_bytes,
)
from app.services.knowledge_object_service import (
    KnowledgeObjectStorageError,
    delete_knowledge_pdf_object,
    store_knowledge_pdf_bytes,
)
from app.services.knowledge_rag_service import (
    KnowledgeRAGError,
    KnowledgeRAGService,
)
from app.services.knowledge_service import (
    KnowledgeMetadataConflictError,
    KnowledgeMetadataError,
    create_knowledge_document,
    delete_knowledge_document,
    update_knowledge_document_status,
)


MAX_KNOWLEDGE_PDF_BYTES = 20 * 1024 * 1024

_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)


class KnowledgeIngestionError(RuntimeError):
    """Raised without exposing backend or storage details."""

    def __init__(self):
        super().__init__(
            "Knowledge PDF ingestion failed."
        )


class KnowledgeIngestionValidationError(
    KnowledgeIngestionError
):
    """Raised when an ingestion request is invalid."""

    def __init__(self):
        RuntimeError.__init__(
            self,
            "Knowledge PDF request is invalid.",
        )


class KnowledgeIngestionConflictError(
    KnowledgeIngestionError
):
    """Raised when identical Knowledge PDF content exists."""

    def __init__(self):
        RuntimeError.__init__(
            self,
            "Knowledge PDF already exists.",
        )


def _title(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeIngestionValidationError()

    candidate = value.strip()

    if (
        not candidate
        or len(candidate) > 255
    ):
        raise KnowledgeIngestionValidationError()

    return candidate


def _filename(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeIngestionValidationError()

    candidate = value.strip()

    if not candidate:
        raise KnowledgeIngestionValidationError()

    safe_name = Path(
        candidate.replace("\\", "/")
    ).name.strip()

    if (
        not safe_name
        or safe_name in {".", ".."}
        or len(safe_name) > 255
        or Path(safe_name).suffix.casefold()
        != ".pdf"
    ):
        raise KnowledgeIngestionValidationError()

    return safe_name


def _knowledge_id(value: Any) -> str:
    candidate = str(value or "").strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeIngestionValidationError()

    return candidate


def _pdf_bytes(value: Any) -> bytes:
    if not isinstance(
        value,
        (bytes, bytearray),
    ):
        raise KnowledgeIngestionValidationError()

    payload = bytes(value)

    if (
        not payload
        or len(payload)
        > MAX_KNOWLEDGE_PDF_BYTES
        or b"%PDF-" not in payload[:1024]
    ):
        raise KnowledgeIngestionValidationError()

    return payload


def _nonnegative_integer(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise KnowledgeIngestionError()

    return value


def _required_result_text(
    value: Any,
    *,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise KnowledgeIngestionError()

    candidate = value.strip()

    if (
        not candidate
        or len(candidate) > maximum_length
    ):
        raise KnowledgeIngestionError()

    return candidate


def _public_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        knowledge_id = _required_result_text(
            record["knowledge_id"],
            maximum_length=128,
        )
        title = _required_result_text(
            record["title"],
            maximum_length=255,
        )
        filename = _filename(
            record["filename"]
        )
        file_size = _nonnegative_integer(
            record["file_size"]
        )
        page_count = _nonnegative_integer(
            record["page_count"]
        )
        chunk_count = _nonnegative_integer(
            record["chunk_count"]
        )
        status = _required_result_text(
            record["status"],
            maximum_length=32,
        ).casefold()
        is_enabled = record["is_enabled"]
        created_at = _required_result_text(
            record["created_at"],
            maximum_length=64,
        )
        updated_at = _required_result_text(
            record["updated_at"],
            maximum_length=64,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        KnowledgeIngestionError,
    ) as error:
        raise KnowledgeIngestionError() from error

    if (
        not _KNOWLEDGE_ID_PATTERN.fullmatch(
            knowledge_id
        )
        or status != "ready"
        or not isinstance(
            is_enabled,
            bool,
        )
    ):
        raise KnowledgeIngestionError()

    return {
        "knowledge_id": knowledge_id,
        "title": title,
        "filename": filename,
        "file_size": file_size,
        "page_count": page_count,
        "chunk_count": chunk_count,
        "status": status,
        "is_enabled": is_enabled,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _mark_failed_safely(
    knowledge_id: str,
    *,
    update_status_fn: Callable,
) -> None:
    try:
        update_status_fn(
            knowledge_id,
            "failed",
        )
    except Exception:
        pass


def _delete_object_safely(
    record: Mapping[str, Any],
    *,
    storage: Any,
    delete_object_fn: Callable,
) -> bool:
    try:
        delete_object_fn(
            record,
            storage=storage,
        )
        return True
    except Exception:
        return False


def _delete_metadata_safely(
    knowledge_id: str,
    *,
    delete_metadata_fn: Callable,
) -> bool:
    try:
        delete_metadata_fn(
            knowledge_id
        )
        return True
    except Exception:
        return False


def _cleanup_after_metadata(
    record: Mapping[str, Any],
    *,
    rag: Any,
    storage: Any,
    delete_object_fn: Callable,
    delete_metadata_fn: Callable,
    update_status_fn: Callable,
) -> bool:
    try:
        knowledge_id = _knowledge_id(
            record["knowledge_id"]
        )
        filename = _filename(
            record["filename"]
        )
    except (
        KeyError,
        TypeError,
        KnowledgeIngestionValidationError,
    ):
        return False

    try:
        rag.delete_document(
            knowledge_id=knowledge_id,
            filename=filename,
        )
    except Exception:
        _mark_failed_safely(
            knowledge_id,
            update_status_fn=(
                update_status_fn
            ),
        )
        return False

    if not _delete_object_safely(
        record,
        storage=storage,
        delete_object_fn=(
            delete_object_fn
        ),
    ):
        _mark_failed_safely(
            knowledge_id,
            update_status_fn=(
                update_status_fn
            ),
        )
        return False

    if not _delete_metadata_safely(
        knowledge_id,
        delete_metadata_fn=(
            delete_metadata_fn
        ),
    ):
        _mark_failed_safely(
            knowledge_id,
            update_status_fn=(
                update_status_fn
            ),
        )
        return False

    return True


def ingest_knowledge_pdf(
    title: str,
    filename: str,
    data: bytes,
    *,
    knowledge_id: str | None = None,
    id_factory: Callable[[], Any] = uuid4,
    storage: Any = None,
    rag: Any = None,
    rag_factory: Callable[[], Any] = (
        KnowledgeRAGService
    ),
    store_pdf_fn: Callable = (
        store_knowledge_pdf_bytes
    ),
    delete_object_fn: Callable = (
        delete_knowledge_pdf_object
    ),
    create_metadata_fn: Callable = (
        create_knowledge_document
    ),
    update_status_fn: Callable = (
        update_knowledge_document_status
    ),
    delete_metadata_fn: Callable = (
        delete_knowledge_document
    ),
    materialize_fn: Callable[
        [bytes, str],
        AbstractContextManager,
    ] = materialize_pdf_bytes,
) -> dict[str, Any]:
    """Ingest one PDF through object, metadata, and vector layers."""

    resolved_title = _title(title)
    resolved_filename = _filename(
        filename
    )
    payload = _pdf_bytes(data)

    try:
        resolved_id = _knowledge_id(
            knowledge_id
            if knowledge_id is not None
            else id_factory()
        )
    except KnowledgeIngestionValidationError:
        raise
    except Exception as error:
        raise (
            KnowledgeIngestionValidationError()
        ) from error

    file_hash = hashlib.sha256(
        payload
    ).hexdigest()
    file_size = len(payload)

    try:
        resolved_rag = (
            rag
            if rag is not None
            else rag_factory()
        )
    except Exception as error:
        raise KnowledgeIngestionError() from error

    object_key = None
    fallback_record: dict[str, Any] | None = None
    metadata_record: Mapping[
        str,
        Any,
    ] | None = None

    try:
        object_key = store_pdf_fn(
            knowledge_id=resolved_id,
            filename=resolved_filename,
            file_hash=file_hash,
            data=payload,
            storage=storage,
        )
        fallback_record = {
            "knowledge_id": resolved_id,
            "filename": resolved_filename,
            "object_key": object_key,
        }
    except (
        KnowledgeObjectStorageError,
        Exception,
    ) as error:
        raise KnowledgeIngestionError() from error

    try:
        metadata_record = (
            create_metadata_fn(
                title=resolved_title,
                filename=resolved_filename,
                object_key=object_key,
                file_hash=file_hash,
                file_size=file_size,
                knowledge_id=resolved_id,
            )
        )
    except KnowledgeMetadataConflictError as error:
        cleaned = _delete_object_safely(
            fallback_record,
            storage=storage,
            delete_object_fn=(
                delete_object_fn
            ),
        )

        if not cleaned:
            raise KnowledgeIngestionError() from error

        raise (
            KnowledgeIngestionConflictError()
        ) from error
    except Exception as error:
        object_cleaned = (
            _delete_object_safely(
                fallback_record,
                storage=storage,
                delete_object_fn=(
                    delete_object_fn
                ),
            )
        )
        metadata_cleaned = (
            _delete_metadata_safely(
                resolved_id,
                delete_metadata_fn=(
                    delete_metadata_fn
                ),
            )
        )

        if not (
            object_cleaned
            and metadata_cleaned
        ):
            raise KnowledgeIngestionError() from error

        raise KnowledgeIngestionError() from error

    try:
        if not isinstance(
            metadata_record,
            Mapping,
        ):
            raise KnowledgeIngestionError()

        record_id = _knowledge_id(
            metadata_record[
                "knowledge_id"
            ]
        )
        record_filename = _filename(
            metadata_record["filename"]
        )
        record_object_key = (
            metadata_record["object_key"]
        )
        record_hash = (
            metadata_record["file_hash"]
        )
        record_size = (
            metadata_record["file_size"]
        )
        record_status = (
            metadata_record["status"]
        )

        if (
            record_id != resolved_id
            or record_filename
            != resolved_filename
            or record_object_key
            != object_key
            or record_hash != file_hash
            or record_size != file_size
            or record_status
            != "processing"
        ):
            raise KnowledgeIngestionError()

        with materialize_fn(
            payload,
            resolved_filename,
        ) as temporary_pdf:
            index_result = (
                resolved_rag.index_pdf(
                    file_path=(
                        temporary_pdf
                    ),
                    knowledge_id=(
                        resolved_id
                    ),
                )
            )

        if not isinstance(
            index_result,
            Mapping,
        ):
            raise KnowledgeIngestionError()

        page_count = (
            _nonnegative_integer(
                index_result["pages"]
            )
        )
        chunk_count = (
            _nonnegative_integer(
                index_result["chunks"]
            )
        )

        ready_record = update_status_fn(
            resolved_id,
            "ready",
            page_count=page_count,
            chunk_count=chunk_count,
        )

        if not isinstance(
            ready_record,
            Mapping,
        ):
            raise KnowledgeIngestionError()

        result = _public_record(
            ready_record
        )

        if (
            result["knowledge_id"]
            != resolved_id
            or result["filename"]
            != resolved_filename
            or result["file_size"]
            != file_size
            or result["page_count"]
            != page_count
            or result["chunk_count"]
            != chunk_count
        ):
            raise KnowledgeIngestionError()

        return result
    except Exception as error:
        cleanup_record = (
            metadata_record
            if isinstance(
                metadata_record,
                Mapping,
            )
            else fallback_record
        )

        cleaned = _cleanup_after_metadata(
            cleanup_record,
            rag=resolved_rag,
            storage=storage,
            delete_object_fn=(
                delete_object_fn
            ),
            delete_metadata_fn=(
                delete_metadata_fn
            ),
            update_status_fn=(
                update_status_fn
            ),
        )

        if not cleaned:
            raise KnowledgeIngestionError() from error

        raise KnowledgeIngestionError() from error
