"""Dedicated object namespace for reusable Knowledge Library PDFs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.services.document_object_service import (
    get_document_storage,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
    normalize_object_key,
)


KNOWLEDGE_OBJECT_PREFIX = "knowledge/documents"

_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)
_FILE_HASH_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class KnowledgeObjectStorageError(RuntimeError):
    """Raised without exposing storage paths or credentials."""

    def __init__(self):
        super().__init__(
            "Knowledge object storage operation failed."
        )


class KnowledgeObjectNotFoundError(
    KnowledgeObjectStorageError
):
    """Raised when a durable Knowledge PDF object is missing."""

    def __init__(self):
        RuntimeError.__init__(
            self,
            "Knowledge PDF object was not found.",
        )


def _knowledge_id(value: Any) -> str:
    candidate = str(value or "").strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeObjectStorageError()

    return candidate


def _pdf_filename(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeObjectStorageError()

    candidate = value.strip()

    if not candidate:
        raise KnowledgeObjectStorageError()

    safe_name = candidate.replace(
        "\\",
        "/",
    ).rsplit(
        "/",
        1,
    )[-1].strip()

    if (
        not safe_name
        or safe_name in {".", ".."}
        or len(safe_name) > 255
        or not safe_name.casefold().endswith(
            ".pdf"
        )
    ):
        raise KnowledgeObjectStorageError()

    return safe_name


def _file_hash(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeObjectStorageError()

    candidate = value.strip().casefold()

    if not _FILE_HASH_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeObjectStorageError()

    return candidate


def _pdf_bytes(value: Any) -> bytes:
    if not isinstance(
        value,
        (bytes, bytearray),
    ):
        raise KnowledgeObjectStorageError()

    payload = bytes(value)

    if (
        not payload
        or b"%PDF-" not in payload[:1024]
    ):
        raise KnowledgeObjectStorageError()

    return payload


def _record_object_key(
    record: Mapping[str, Any],
) -> str:
    try:
        raw_key = record["object_key"]
    except (
        KeyError,
        TypeError,
    ) as error:
        raise KnowledgeObjectStorageError() from error

    if not isinstance(raw_key, str):
        raise KnowledgeObjectStorageError()

    try:
        key = normalize_object_key(
            raw_key
        )
    except (
        TypeError,
        ValueError,
        DocumentStorageError,
    ) as error:
        raise KnowledgeObjectStorageError() from error

    prefix = (
        f"{KNOWLEDGE_OBJECT_PREFIX}/"
    )

    if not key.startswith(prefix):
        raise KnowledgeObjectStorageError()

    return key


def build_knowledge_object_key(
    *,
    knowledge_id: str,
    filename: str,
    file_hash: str,
) -> str:
    """Build an immutable object key outside chat storage paths."""

    resolved_id = _knowledge_id(
        knowledge_id
    )
    resolved_filename = _pdf_filename(
        filename
    )
    resolved_hash = _file_hash(
        file_hash
    )

    try:
        return normalize_object_key(
            f"{KNOWLEDGE_OBJECT_PREFIX}/"
            f"{resolved_id}/"
            f"{resolved_hash}/"
            f"{resolved_filename}"
        )
    except (
        TypeError,
        ValueError,
        DocumentStorageError,
    ) as error:
        raise KnowledgeObjectStorageError() from error


def store_knowledge_pdf_bytes(
    *,
    knowledge_id: str,
    filename: str,
    file_hash: str,
    data: bytes,
    storage=None,
) -> str:
    """Store one immutable Knowledge PDF in configured storage."""

    key = build_knowledge_object_key(
        knowledge_id=knowledge_id,
        filename=filename,
        file_hash=file_hash,
    )
    payload = _pdf_bytes(data)
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    try:
        stored_key = (
            resolved_storage.put_bytes(
                key,
                payload,
                content_type=(
                    "application/pdf"
                ),
            )
        )
        normalized_stored_key = (
            normalize_object_key(
                stored_key
            )
        )
    except (
        DocumentStorageError,
        DocumentNotFoundError,
        TypeError,
        ValueError,
    ) as error:
        raise KnowledgeObjectStorageError() from error
    except Exception as error:
        raise KnowledgeObjectStorageError() from error

    if normalized_stored_key != key:
        try:
            resolved_storage.delete(
                normalized_stored_key
            )
        except Exception:
            pass

        raise KnowledgeObjectStorageError()

    return key


def read_knowledge_pdf_bytes(
    record: Mapping[str, Any],
    *,
    storage=None,
) -> bytes:
    """Read one Knowledge PDF using its durable metadata record."""

    key = _record_object_key(record)
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    try:
        payload = resolved_storage.get_bytes(
            key
        )
    except DocumentNotFoundError as error:
        raise KnowledgeObjectNotFoundError() from error
    except DocumentStorageError as error:
        raise KnowledgeObjectStorageError() from error
    except Exception as error:
        raise KnowledgeObjectStorageError() from error

    try:
        return _pdf_bytes(payload)
    except KnowledgeObjectStorageError as error:
        raise KnowledgeObjectStorageError() from error


def delete_knowledge_pdf_object(
    record: Mapping[str, Any],
    *,
    storage=None,
) -> bool:
    """Delete one Knowledge PDF idempotently."""

    key = _record_object_key(record)
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    try:
        return bool(
            resolved_storage.delete(key)
        )
    except DocumentNotFoundError:
        return False
    except DocumentStorageError as error:
        raise KnowledgeObjectStorageError() from error
    except Exception as error:
        raise KnowledgeObjectStorageError() from error
