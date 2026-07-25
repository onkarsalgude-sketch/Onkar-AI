"""Authenticated bounded controls for existing conversational memory."""

from __future__ import annotations

import hashlib
import hmac
import os
import re

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    status,
)

from app.memory.memory import (
    MemoryPersistenceError,
    clear,
    get,
)
from app.models.memory import (
    MemoryClearResponse,
    MemoryListResponse,
    MemoryPreview,
)


router = APIRouter(
    prefix="/memory",
    tags=["memory"],
)

_MEMORY_PREVIEW_LIMIT = 240
_MEMORY_TOKEN_DIGEST_ENV = (
    "MEMORY_API_TOKEN_SHA256"
)
_SHA256_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def _memory_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Memory is unavailable.",
    )


def _memory_unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Memory authorization failed.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def _configured_digest() -> str:
    digest = str(
        os.environ.get(
            _MEMORY_TOKEN_DIGEST_ENV,
            "",
        )
    ).strip()

    if not _SHA256_PATTERN.fullmatch(
        digest
    ):
        raise _memory_unavailable()

    return digest.casefold()


def _require_memory_authorization(
    request: Request,
) -> None:
    authorization = str(
        request.headers.get(
            "authorization",
            "",
        )
    ).strip()

    scheme, separator, token = (
        authorization.partition(" ")
    )

    if (
        not separator
        or scheme.casefold() != "bearer"
        or not token.strip()
    ):
        raise _memory_unauthorized()

    supplied_digest = (
        hashlib.sha256(
            token.strip().encode(
                "utf-8"
            )
        )
        .hexdigest()
        .casefold()
    )

    if not hmac.compare_digest(
        supplied_digest,
        _configured_digest(),
    ):
        raise _memory_unauthorized()


def _preview_record(
    record: dict[str, str],
) -> MemoryPreview:
    role = str(
        record.get(
            "role",
            "",
        )
    ).strip()

    content = str(
        record.get(
            "content",
            "",
        )
    ).strip()

    if not role or not content:
        raise MemoryPersistenceError()

    truncated = (
        len(content) >
        _MEMORY_PREVIEW_LIMIT
    )

    return MemoryPreview(
        role=role,
        preview=content[
            :_MEMORY_PREVIEW_LIMIT
        ],
        truncated=truncated,
    )


@router.get(
    "",
    response_model=MemoryListResponse,
)
def read_memory(
    request: Request,
    limit: int = Query(
        default=6,
        ge=1,
        le=20,
    ),
) -> MemoryListResponse:
    _require_memory_authorization(
        request
    )

    try:
        records = get(
            limit=limit,
        )

        items = [
            _preview_record(record)
            for record in records
        ]

        return MemoryListResponse(
            items=items,
            returned=len(items),
            limit=limit,
        )

    except HTTPException:
        raise

    except MemoryPersistenceError as error:
        raise _memory_unavailable() from error

    except Exception as error:
        raise _memory_unavailable() from error


@router.delete(
    "",
    response_model=MemoryClearResponse,
)
def clear_memory(
    request: Request,
) -> MemoryClearResponse:
    _require_memory_authorization(
        request
    )

    try:
        clear()

        return MemoryClearResponse(
            cleared=True,
            message="Memory cleared.",
        )

    except HTTPException:
        raise

    except MemoryPersistenceError as error:
        raise _memory_unavailable() from error

    except Exception as error:
        raise _memory_unavailable() from error
