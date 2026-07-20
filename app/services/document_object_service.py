"""High-level durable storage operations for uploaded documents."""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from app.config.settings import UPLOAD_DIR
from app.config.storage import (
    load_document_storage_settings,
)
from app.services.document_service import (
    list_documents,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
    LocalDocumentStorage,
    build_document_storage,
    normalize_object_key,
)


_DOCUMENT_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)

_FILE_HASH_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


def _safe_filename(
    filename: str,
) -> str:
    candidate = str(filename)

    if (
        not candidate
        or candidate != Path(candidate).name
        or len(candidate) > 255
        or any(
            ord(character) < 32
            or ord(character) == 127
            for character in candidate
        )
    ):
        raise ValueError(
            "Invalid document filename."
        )

    return candidate


def build_document_object_key(
    *,
    chat_id: int,
    document_id: str,
    filename: str,
    file_hash: str,
) -> str:
    """Build an immutable object key for one PDF version."""
    if chat_id <= 0:
        raise ValueError(
            "Invalid chat ID."
        )

    normalized_document_id = str(
        document_id
    ).strip()

    if not _DOCUMENT_ID_PATTERN.fullmatch(
        normalized_document_id
    ):
        raise ValueError(
            "Invalid document ID."
        )

    normalized_hash = str(
        file_hash
    ).strip().casefold()

    if not _FILE_HASH_PATTERN.fullmatch(
        normalized_hash
    ):
        raise ValueError(
            "Invalid document file hash."
        )

    safe_filename = _safe_filename(
        filename
    )

    return normalize_object_key(
        f"chats/{chat_id}/documents/"
        f"{normalized_document_id}/"
        f"{normalized_hash}/"
        f"{safe_filename}"
    )


@lru_cache(maxsize=1)
def get_document_storage():
    """Return the configured process-wide document storage backend."""
    settings = load_document_storage_settings(
        default_local_root=UPLOAD_DIR
    )

    return build_document_storage(
        settings
    )


def reset_document_storage_cache() -> None:
    """Clear the storage singleton, primarily for isolated tests."""
    get_document_storage.cache_clear()


def store_document_bytes(
    *,
    chat_id: int,
    document_id: str,
    filename: str,
    file_hash: str,
    data: bytes,
    storage=None,
) -> str:
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    key = build_document_object_key(
        chat_id=chat_id,
        document_id=document_id,
        filename=filename,
        file_hash=file_hash,
    )

    return resolved_storage.put_bytes(
        key,
        data,
        content_type="application/pdf",
    )


def _canonical_key(
    reference: object,
) -> str | None:
    try:
        return normalize_object_key(
            str(reference)
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _legacy_local_paths(
    document: dict[str, Any],
    storage,
) -> list[Path]:
    if not isinstance(
        storage,
        LocalDocumentStorage,
    ):
        return []

    chat_id = int(
        document.get("chat_id", 0)
        or 0
    )

    filename = _safe_filename(
        str(
            document.get(
                "filename",
                "",
            )
        )
    )

    if chat_id <= 0:
        return []

    roots = {
        storage.root.resolve(
            strict=False
        ),
        Path(UPLOAD_DIR).resolve(
            strict=False
        ),
    }

    expected_paths = {
        (
            root
            / f"chat_{chat_id}"
            / filename
        ).resolve(strict=False)
        for root in roots
    }

    reference = str(
        document.get(
            "file_path",
            "",
        )
    ).strip()

    candidates = set(
        expected_paths
    )

    if reference:
        raw_path = Path(reference)

        if raw_path.is_absolute():
            candidates.add(
                raw_path.resolve(
                    strict=False
                )
            )
        else:
            candidates.add(
                (
                    Path.cwd()
                    / raw_path
                ).resolve(
                    strict=False
                )
            )

    return [
        candidate
        for candidate in candidates
        if candidate in expected_paths
    ]


def read_document_bytes(
    document: dict[str, Any],
    *,
    storage=None,
) -> bytes:
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    reference = document.get(
        "file_path",
        "",
    )

    key = _canonical_key(
        reference
    )

    if key is not None:
        try:
            return resolved_storage.get_bytes(
                key
            )
        except DocumentNotFoundError:
            pass

    for candidate in _legacy_local_paths(
        document,
        resolved_storage,
    ):
        try:
            return candidate.read_bytes()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise DocumentStorageError(
                "Legacy document could not be read."
            ) from error

    raise DocumentNotFoundError(
        "Document object was not found."
    )


def delete_document_object(
    document: dict[str, Any],
    *,
    storage=None,
) -> bool:
    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    reference = document.get(
        "file_path",
        "",
    )

    key = _canonical_key(
        reference
    )

    if key is not None:
        deleted = resolved_storage.delete(
            key
        )

        if deleted:
            return True

    for candidate in _legacy_local_paths(
        document,
        resolved_storage,
    ):
        if not candidate.is_file():
            continue

        try:
            candidate.unlink()
        except OSError as error:
            raise DocumentStorageError(
                "Legacy document could not be deleted."
            ) from error

        parent = candidate.parent

        try:
            parent.rmdir()
        except OSError:
            pass

        return True

    return False


def delete_chat_document_objects(
    chat_id: int,
    *,
    storage=None,
) -> dict[str, int]:
    if chat_id <= 0:
        raise ValueError(
            "Invalid chat ID."
        )

    resolved_storage = (
        storage
        if storage is not None
        else get_document_storage()
    )

    documents = list_documents(
        chat_id
    )

    deleted = 0
    missing = 0

    for document in documents:
        if delete_document_object(
            document,
            storage=resolved_storage,
        ):
            deleted += 1
        else:
            missing += 1

    return {
        "attempted": len(documents),
        "deleted": deleted,
        "missing": missing,
    }


@contextmanager
def materialize_pdf_bytes(
    data: bytes,
    filename: str,
) -> Iterator[Path]:
    """Create a temporary local PDF needed by pypdf/Chroma."""
    if not isinstance(
        data,
        bytes,
    ):
        raise TypeError(
            "Document data must be bytes."
        )

    safe_filename = _safe_filename(
        filename
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=(
                "-"
                + safe_filename
            ),
            delete=False,
        ) as temporary_file:
            temporary_file.write(
                data
            )

            temporary_path = Path(
                temporary_file.name
            )

        yield temporary_path

    finally:
        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True
            )


def restore_document_vectors(
    document: dict[str, Any],
    *,
    rag,
    storage=None,
) -> bool:
    """Re-index a previous object during replacement rollback."""
    data = read_document_bytes(
        document,
        storage=storage,
    )

    with materialize_pdf_bytes(
        data,
        str(document["filename"]),
    ) as temporary_path:
        result = rag.add_pdf(
            file_path=temporary_path,
            chat_id=int(
                document["chat_id"]
            ),
            document_id=str(
                document["document_id"]
            ),
        )

    return int(
        result.get(
            "chunks",
            0,
        )
        or 0
    ) > 0
