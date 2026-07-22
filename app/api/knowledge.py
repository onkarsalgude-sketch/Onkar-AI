"""Sanitized Knowledge Library metadata API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    status as http_status,
)
from pydantic import BaseModel, ConfigDict

from app.services.knowledge_delete_service import (
    KnowledgeDeleteError,
    KnowledgeDeleteValidationError,
    delete_knowledge_pdf as delete_pdf,
)
from app.services.knowledge_ingestion_service import (
    MAX_KNOWLEDGE_PDF_BYTES,
    KnowledgeIngestionConflictError,
    KnowledgeIngestionError,
    KnowledgeIngestionValidationError,
    ingest_knowledge_pdf as ingest_pdf,
)
from app.services.knowledge_service import (
    ALLOWED_KNOWLEDGE_STATUSES,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    KnowledgeMetadataConflictError,
    KnowledgeMetadataError,
    create_knowledge_document as create_metadata_record,
    get_knowledge_document as get_metadata_record,
    list_knowledge_documents as list_metadata_records,
    set_knowledge_document_enabled as set_metadata_enabled,
    update_knowledge_document_status as update_metadata_status,
)


_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)


router = APIRouter(tags=["knowledge"])


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")




class KnowledgeStatusRequest(_StrictRequest):
    status: Any
    page_count: Any = None
    chunk_count: Any = None


class KnowledgeEnabledRequest(_StrictRequest):
    is_enabled: Any


class KnowledgeDocumentResponse(BaseModel):
    knowledge_id: str
    title: str
    filename: str
    file_size: int
    page_count: int
    chunk_count: int
    status: str
    is_enabled: bool
    created_at: str
    updated_at: str


class KnowledgeDeleteResponse(BaseModel):
    knowledge_id: str
    deleted: bool


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = (
        "private, no-store"
    )
    response.headers["X-Content-Type-Options"] = (
        "nosniff"
    )


def _bad_request() -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail="Invalid knowledge request",
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Knowledge document not found",
    )


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_409_CONFLICT,
        detail="Knowledge document already exists",
    )


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=(
            http_status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail="Knowledge metadata is unavailable",
    )


def _required_text(
    value: Any,
    *,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise _bad_request()

    candidate = value.strip()

    if (
        not candidate
        or len(candidate) > maximum_length
    ):
        raise _bad_request()

    return candidate


def _knowledge_id(value: Any) -> str:
    if not isinstance(value, str):
        raise _bad_request()

    candidate = value.strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise _bad_request()

    return candidate


def _filename(value: Any) -> str:
    candidate = _required_text(
        value,
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
        raise _bad_request()

    return safe_name


def _file_hash(value: Any) -> str:
    if not isinstance(value, str):
        raise _bad_request()

    candidate = value.strip().casefold()

    if (
        len(candidate) != 64
        or any(
            character not in "0123456789abcdef"
            for character in candidate
        )
    ):
        raise _bad_request()

    return candidate


def _nonnegative_integer(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise _bad_request()

    return value


def _status(value: Any) -> str:
    if not isinstance(value, str):
        raise _bad_request()

    candidate = value.strip().casefold()

    if candidate not in ALLOWED_KNOWLEDGE_STATUSES:
        raise _bad_request()

    return candidate


def _enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _bad_request()

    return value


def _public_record(
    record: Any,
) -> KnowledgeDocumentResponse:
    if not isinstance(record, dict):
        raise _service_unavailable()

    try:
        return KnowledgeDocumentResponse(
            knowledge_id=str(
                record["knowledge_id"]
            ),
            title=str(record["title"]),
            filename=str(record["filename"]),
            file_size=int(record["file_size"]),
            page_count=int(record["page_count"]),
            chunk_count=int(record["chunk_count"]),
            status=str(record["status"]),
            is_enabled=bool(
                record["is_enabled"]
            ),
            created_at=str(record["created_at"]),
            updated_at=str(record["updated_at"]),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise _service_unavailable() from error


@router.post(
    "/knowledge",
    response_model=KnowledgeDocumentResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def upload_knowledge_pdf(
    response: Response,
    title: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> KnowledgeDocumentResponse:
    if file is None:
        raise _bad_request()

    media_type = str(
        file.content_type or ""
    ).split(
        ";",
        1,
    )[0].strip().casefold()

    if media_type != "application/pdf":
        raise _bad_request()

    try:
        payload = await file.read(
            MAX_KNOWLEDGE_PDF_BYTES + 1
        )
    except Exception as error:
        raise _service_unavailable() from error
    finally:
        try:
            await file.close()
        except Exception:
            pass

    if len(payload) > MAX_KNOWLEDGE_PDF_BYTES:
        raise HTTPException(
            status_code=(
                http_status
                .HTTP_413_REQUEST_ENTITY_TOO_LARGE
            ),
            detail="Knowledge PDF is too large.",
        )

    try:
        record = ingest_pdf(
            title=title,
            filename=file.filename,
            data=payload,
        )
    except (
        KnowledgeIngestionValidationError
    ) as error:
        raise _bad_request() from error
    except (
        KnowledgeIngestionConflictError
    ) as error:
        raise _conflict() from error
    except KnowledgeIngestionError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    _set_no_store(response)
    return _public_record(record)


@router.get(
    "/knowledge",
    response_model=list[KnowledgeDocumentResponse],
)
def list_knowledge_metadata(
    response: Response,
    limit: int = Query(
        DEFAULT_LIST_LIMIT,
        ge=1,
        le=MAX_LIST_LIMIT,
    ),
    status: str | None = Query(
        None,
    ),
    enabled: bool | None = Query(
        None,
    ),
) -> list[KnowledgeDocumentResponse]:
    normalized_status = (
        _status(status)
        if status is not None
        else None
    )

    try:
        records = list_metadata_records(
            limit=limit,
            status=normalized_status,
            enabled=enabled,
        )
    except KnowledgeMetadataError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    if not isinstance(records, list):
        raise _service_unavailable()

    _set_no_store(response)
    return [
        _public_record(record)
        for record in records
    ]


@router.get(
    "/knowledge/{knowledge_id}",
    response_model=KnowledgeDocumentResponse,
)
def get_knowledge_metadata(
    knowledge_id: str,
    response: Response,
) -> KnowledgeDocumentResponse:
    normalized_id = _knowledge_id(
        knowledge_id
    )

    try:
        record = get_metadata_record(
            normalized_id
        )
    except KnowledgeMetadataError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    if record is None:
        raise _not_found()

    _set_no_store(response)
    return _public_record(record)


@router.patch(
    "/knowledge/{knowledge_id}/status",
    response_model=KnowledgeDocumentResponse,
)
def update_knowledge_status(
    knowledge_id: str,
    request: KnowledgeStatusRequest,
    response: Response,
) -> KnowledgeDocumentResponse:
    normalized_id = _knowledge_id(
        knowledge_id
    )
    normalized_status = _status(
        request.status
    )

    if normalized_status == "ready":
        if (
            request.page_count is None
            or request.chunk_count is None
        ):
            raise _bad_request()

        page_count = _nonnegative_integer(
            request.page_count
        )
        chunk_count = _nonnegative_integer(
            request.chunk_count
        )
    else:
        if (
            request.page_count is not None
            or request.chunk_count is not None
        ):
            raise _bad_request()

        page_count = None
        chunk_count = None

    try:
        record = update_metadata_status(
            normalized_id,
            normalized_status,
            page_count=page_count,
            chunk_count=chunk_count,
        )
    except KnowledgeMetadataError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    if record is None:
        raise _not_found()

    _set_no_store(response)
    return _public_record(record)


@router.put(
    "/knowledge/{knowledge_id}/enabled",
    response_model=KnowledgeDocumentResponse,
)
def update_knowledge_enabled(
    knowledge_id: str,
    request: KnowledgeEnabledRequest,
    response: Response,
) -> KnowledgeDocumentResponse:
    normalized_id = _knowledge_id(
        knowledge_id
    )
    normalized_enabled = _enabled(
        request.is_enabled
    )

    try:
        record = set_metadata_enabled(
            normalized_id,
            normalized_enabled,
        )
    except KnowledgeMetadataError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    if record is None:
        raise _not_found()

    _set_no_store(response)
    return _public_record(record)


@router.delete(
    "/knowledge/{knowledge_id}",
    response_model=KnowledgeDeleteResponse,
)
def delete_knowledge_metadata(
    knowledge_id: str,
    response: Response,
) -> KnowledgeDeleteResponse:
    normalized_id = _knowledge_id(
        knowledge_id
    )

    try:
        result = delete_pdf(
            normalized_id
        )
    except (
        KnowledgeDeleteValidationError
    ) as error:
        raise _bad_request() from error
    except KnowledgeDeleteError as error:
        raise _service_unavailable() from error
    except Exception as error:
        raise _service_unavailable() from error

    if not isinstance(result, dict):
        raise _service_unavailable()

    try:
        result_id = result["knowledge_id"]
        deleted = result["deleted"]
    except (
        KeyError,
        TypeError,
    ) as error:
        raise _service_unavailable() from error

    if (
        not isinstance(result_id, str)
        or result_id != normalized_id
        or not isinstance(deleted, bool)
    ):
        raise _service_unavailable()

    _set_no_store(response)
    return KnowledgeDeleteResponse(
        knowledge_id=result_id,
        deleted=deleted,
    )
