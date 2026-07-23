"""Durable, resumable deletion for reusable Knowledge PDFs."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.services.knowledge_object_service import (
    delete_knowledge_pdf_object,
)
from app.services.knowledge_rag_service import (
    KnowledgeRAGService,
)
from app.services.knowledge_service import (
    delete_knowledge_document as delete_metadata_record,
    get_knowledge_document as get_metadata_record,
    update_knowledge_document_status as update_metadata_status,
)


_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)
_KNOWLEDGE_OBJECT_PREFIX = "knowledge/documents"


class KnowledgeDeleteError(RuntimeError):
    """Raised without exposing storage, vector, or database details."""

    def __init__(self):
        super().__init__(
            "Knowledge document deletion failed."
        )


class KnowledgeDeleteValidationError(
    KnowledgeDeleteError
):
    """Raised when a Knowledge delete request is invalid."""

    def __init__(self):
        RuntimeError.__init__(
            self,
            "Knowledge delete request is invalid.",
        )


def _knowledge_id(value: Any) -> str:
    candidate = str(value or "").strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeDeleteValidationError()

    return candidate


def _pdf_filename(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeDeleteError()

    candidate = value.strip()

    if not candidate:
        raise KnowledgeDeleteError()

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
        raise KnowledgeDeleteError()

    return safe_name


def _object_key(
    value: Any,
    *,
    knowledge_id: str,
) -> str:
    if not isinstance(value, str):
        raise KnowledgeDeleteError()

    candidate = value.strip().replace(
        "\\",
        "/",
    )

    expected_prefix = (
        f"{_KNOWLEDGE_OBJECT_PREFIX}/"
        f"{knowledge_id}/"
    )

    if (
        not candidate
        or len(candidate) > 1024
        or not candidate.startswith(
            expected_prefix
        )
        or "/../" in f"/{candidate}/"
        or "/./" in f"/{candidate}/"
    ):
        raise KnowledgeDeleteError()

    return candidate


def _record(
    value: Any,
    *,
    expected_id: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise KnowledgeDeleteError()

    try:
        record_id = _knowledge_id(
            value["knowledge_id"]
        )
        filename = _pdf_filename(
            value["filename"]
        )
        object_key = _object_key(
            value["object_key"],
            knowledge_id=record_id,
        )
        status = str(
            value["status"]
        ).strip().casefold()
    except (
        KeyError,
        TypeError,
        ValueError,
        KnowledgeDeleteError,
    ) as error:
        raise KnowledgeDeleteError() from error

    if (
        record_id != expected_id
        or status not in {
            "processing",
            "ready",
            "failed",
            "deleting",
        }
    ):
        raise KnowledgeDeleteError()

    result = dict(value)
    result["knowledge_id"] = record_id
    result["filename"] = filename
    result["object_key"] = object_key
    result["status"] = status
    return result


def _delete_result(
    knowledge_id: str,
    *,
    deleted: bool,
) -> dict[str, Any]:
    return {
        "knowledge_id": knowledge_id,
        "deleted": bool(deleted),
    }


def delete_knowledge_pdf(
    knowledge_id: str,
    *,
    storage: Any = None,
    rag: Any = None,
    rag_factory: Callable[[], Any] = (
        KnowledgeRAGService
    ),
    get_metadata_fn: Callable = (
        get_metadata_record
    ),
    update_status_fn: Callable = (
        update_metadata_status
    ),
    delete_object_fn: Callable = (
        delete_knowledge_pdf_object
    ),
    delete_metadata_fn: Callable = (
        delete_metadata_record
    ),
) -> dict[str, Any]:
    """Delete vectors, object bytes, and metadata in retry-safe order."""

    resolved_id = _knowledge_id(
        knowledge_id
    )

    try:
        current = get_metadata_fn(
            resolved_id
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    if current is None:
        return _delete_result(
            resolved_id,
            deleted=False,
        )

    current_record = _record(
        current,
        expected_id=resolved_id,
    )

    try:
        resolved_rag = (
            rag
            if rag is not None
            else rag_factory()
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    try:
        deleting = update_status_fn(
            resolved_id,
            "deleting",
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    if deleting is None:
        return _delete_result(
            resolved_id,
            deleted=False,
        )

    deleting_record = _record(
        deleting,
        expected_id=resolved_id,
    )

    if (
        deleting_record["status"]
        != "deleting"
        or deleting_record["filename"]
        != current_record["filename"]
        or deleting_record["object_key"]
        != current_record["object_key"]
    ):
        raise KnowledgeDeleteError()

    try:
        resolved_rag.delete_document(
            knowledge_id=resolved_id,
            filename=(
                deleting_record["filename"]
            ),
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    try:
        delete_object_fn(
            deleting_record,
            storage=storage,
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    try:
        delete_metadata_fn(
            resolved_id
        )
    except Exception as error:
        raise KnowledgeDeleteError() from error

    return _delete_result(
        resolved_id,
        deleted=True,
    )
