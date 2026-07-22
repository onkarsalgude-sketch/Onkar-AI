from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.services.knowledge_rag_service import (
    MAX_KNOWLEDGE_SEARCH_LIMIT,
    KnowledgeRAGService,
)
from app.services.knowledge_service import (
    MAX_LIST_LIMIT,
    list_knowledge_documents,
)


MAX_KNOWLEDGE_QUERY_LENGTH = 20_000
_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)


class KnowledgeRetrievalError(RuntimeError):
    """Raised when reusable Knowledge retrieval is unavailable."""


class KnowledgeRetrievalValidationError(
    KnowledgeRetrievalError
):
    """Raised when a retrieval request is invalid."""


def _empty_result() -> dict[str, Any]:
    return {
        "context": "",
        "sources": [],
    }


def _query(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeRetrievalValidationError(
            "Invalid knowledge retrieval request."
        )

    candidate = value.strip()

    if (
        not candidate
        or len(candidate)
        > MAX_KNOWLEDGE_QUERY_LENGTH
    ):
        raise KnowledgeRetrievalValidationError(
            "Invalid knowledge retrieval request."
        )

    return candidate


def _limit(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not (
            1
            <= value
            <= MAX_KNOWLEDGE_SEARCH_LIMIT
        )
    ):
        raise KnowledgeRetrievalValidationError(
            "Invalid knowledge retrieval request."
        )

    return value


def _knowledge_id(value: Any) -> str:
    candidate = str(value or "").strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        )

    return candidate


def _selected_document_ids(
    records: Any,
) -> list[str]:
    if not isinstance(records, list):
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        )

    selected: list[str] = []
    seen: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        if (
            record.get("status") != "ready"
            or record.get("is_enabled")
            is not True
        ):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        document_id = _knowledge_id(
            record.get("knowledge_id")
        )

        if document_id in seen:
            continue

        seen.add(document_id)
        selected.append(document_id)

        if len(selected) > MAX_LIST_LIMIT:
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

    return selected


def _safe_page(value: Any) -> int | str | None:
    if value is None:
        return None

    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 1
    ):
        return value

    if isinstance(value, str):
        candidate = value.strip()

        if candidate and len(candidate) <= 64:
            return candidate

    raise KnowledgeRetrievalError(
        "Knowledge retrieval failed."
    )


def _safe_result(
    result: Any,
    *,
    selected_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        )

    context = result.get(
        "context",
        "",
    )
    sources = result.get(
        "sources",
        [],
    )

    if (
        not isinstance(context, str)
        or not isinstance(sources, list)
    ):
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        )

    safe_sources: list[dict[str, Any]] = []

    for source in sources:
        if not isinstance(source, dict):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        if source.get("type") != "pdf":
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        filename = source.get(
            "filename"
        )
        title = source.get(
            "title",
            filename,
        )

        if (
            not isinstance(filename, str)
            or not isinstance(title, str)
        ):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        safe_filename = filename.strip()
        safe_title = title.strip()

        if (
            not safe_filename
            or len(safe_filename) > 255
            or not safe_filename.lower()
            .endswith(".pdf")
            or safe_title != safe_filename
        ):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        knowledge_id = _knowledge_id(
            source.get("knowledge_id")
        )

        if knowledge_id not in selected_ids:
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        safe_sources.append(
            {
                "type": "pdf",
                "title": safe_filename,
                "filename": safe_filename,
                "page": _safe_page(
                    source.get("page")
                ),
                "knowledge_id": knowledge_id,
            }
        )

    return {
        "context": context,
        "sources": safe_sources,
    }


def retrieve_knowledge_context(
    query: str,
    *,
    limit: int = 5,
    db_path: str | None = None,
    connection_factory: Callable | None = None,
    metadata_reader: Callable = (
        list_knowledge_documents
    ),
    rag_factory: Callable = (
        KnowledgeRAGService
    ),
) -> dict[str, Any]:
    """Retrieve enabled, ready reusable Knowledge context."""

    resolved_query = _query(query)
    resolved_limit = _limit(limit)

    metadata_kwargs: dict[str, Any] = {
        "limit": MAX_LIST_LIMIT,
        "status": "ready",
        "enabled": True,
    }

    if db_path is not None:
        metadata_kwargs[
            "db_path"
        ] = db_path

    if connection_factory is not None:
        metadata_kwargs[
            "connection_factory"
        ] = connection_factory

    try:
        records = metadata_reader(
            **metadata_kwargs
        )
    except Exception as error:
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        ) from error

    document_ids = _selected_document_ids(
        records
    )

    if not document_ids:
        return _empty_result()

    try:
        rag = rag_factory()
        search = getattr(
            rag,
            "search",
            None,
        )

        if not callable(search):
            raise KnowledgeRetrievalError(
                "Knowledge retrieval failed."
            )

        result = search(
            resolved_query,
            limit=resolved_limit,
            document_ids=document_ids,
        )
    except KnowledgeRetrievalError:
        raise
    except Exception as error:
        raise KnowledgeRetrievalError(
            "Knowledge retrieval failed."
        ) from error

    return _safe_result(
        result,
        selected_ids=set(
            document_ids
        ),
    )
