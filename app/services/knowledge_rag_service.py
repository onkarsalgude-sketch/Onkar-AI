"""Isolated reusable Knowledge Library vector namespace."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.config.rag import (
    RAGSettings,
    load_rag_settings,
)
from app.config.settings import VECTOR_DB_DIR
from app.services.rag_service import RAGService


KNOWLEDGE_COLLECTION_NAME = "knowledge_documents"
KNOWLEDGE_INTERNAL_SCOPE_ID = 1
MAX_KNOWLEDGE_SEARCH_LIMIT = 20
MAX_KNOWLEDGE_FILENAME_FILTERS = 100

_KNOWLEDGE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
)


class KnowledgeRAGError(RuntimeError):
    """Raised without exposing vector backend details."""

    def __init__(self):
        super().__init__(
            "Knowledge vector operation failed."
        )


def _knowledge_id(value: Any) -> str:
    candidate = str(value or "").strip()

    if not _KNOWLEDGE_ID_PATTERN.fullmatch(
        candidate
    ):
        raise KnowledgeRAGError()

    return candidate


def _pdf_filename(value: Any) -> str:
    candidate = str(value or "").strip()

    if not candidate:
        raise KnowledgeRAGError()

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
        raise KnowledgeRAGError()

    return safe_name


def _pdf_path(value: Any) -> Path:
    candidate = str(value or "").strip()

    if not candidate:
        raise KnowledgeRAGError()

    resolved = Path(candidate)

    if resolved.suffix.casefold() != ".pdf":
        raise KnowledgeRAGError()

    return resolved


def _nonnegative_integer(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise KnowledgeRAGError()

    return value


def _search_limit(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not (
            1
            <= value
            <= MAX_KNOWLEDGE_SEARCH_LIMIT
        )
    ):
        raise KnowledgeRAGError()

    return value


def _query(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeRAGError()

    candidate = value.strip()

    if (
        not candidate
        or len(candidate) > 20_000
    ):
        raise KnowledgeRAGError()

    return candidate


def _filename_filters(
    values: Sequence[str] | None,
) -> list[str] | None:
    if values is None:
        return None

    if isinstance(
        values,
        (str, bytes, bytearray),
    ):
        raise KnowledgeRAGError()

    normalized: list[str] = []

    try:
        candidates = list(values)
    except TypeError as error:
        raise KnowledgeRAGError() from error

    if (
        not candidates
        or len(candidates)
        > MAX_KNOWLEDGE_FILENAME_FILTERS
    ):
        raise KnowledgeRAGError()

    for value in candidates:
        filename = _pdf_filename(value)

        if filename not in normalized:
            normalized.append(filename)

    return normalized


def build_knowledge_rag_settings(
    *,
    base_settings: RAGSettings | None = None,
    settings_loader: Callable[..., RAGSettings] = (
        load_rag_settings
    ),
) -> RAGSettings:
    """Clone global RAG settings into an isolated collection."""

    try:
        resolved = (
            base_settings
            if base_settings is not None
            else settings_loader(
                default_chroma_path=VECTOR_DB_DIR
            )
        )

        if not isinstance(
            resolved,
            RAGSettings,
        ):
            raise TypeError(
                "Unexpected RAG settings type."
            )

        return replace(
            resolved,
            collection_name=(
                KNOWLEDGE_COLLECTION_NAME
            ),
        )
    except KnowledgeRAGError:
        raise
    except Exception as error:
        raise KnowledgeRAGError() from error


def create_knowledge_rag_service(
    *,
    settings: RAGSettings | None = None,
    settings_loader: Callable[..., RAGSettings] = (
        load_rag_settings
    ),
    embedding_function=None,
    pgvector_store=None,
    chroma_client=None,
) -> RAGService:
    """Create RAGService with the dedicated knowledge collection."""

    try:
        knowledge_settings = (
            build_knowledge_rag_settings(
                base_settings=settings,
                settings_loader=settings_loader,
            )
        )

        return RAGService(
            settings=knowledge_settings,
            embedding_function=(
                embedding_function
            ),
            pgvector_store=pgvector_store,
            chroma_client=chroma_client,
        )
    except KnowledgeRAGError:
        raise
    except Exception as error:
        raise KnowledgeRAGError() from error


class KnowledgeRAGService:
    """Scope vector operations to the reusable library."""

    def __init__(
        self,
        *,
        service: Any | None = None,
        settings: RAGSettings | None = None,
        settings_loader: Callable[
            ...,
            RAGSettings,
        ] = load_rag_settings,
        embedding_function=None,
        pgvector_store=None,
        chroma_client=None,
    ):
        try:
            self._service = (
                service
                if service is not None
                else create_knowledge_rag_service(
                    settings=settings,
                    settings_loader=(
                        settings_loader
                    ),
                    embedding_function=(
                        embedding_function
                    ),
                    pgvector_store=(
                        pgvector_store
                    ),
                    chroma_client=(
                        chroma_client
                    ),
                )
            )
        except KnowledgeRAGError:
            raise
        except Exception as error:
            raise KnowledgeRAGError() from error

    @property
    def backend(self) -> str:
        try:
            return str(
                self._service.backend
            )
        except Exception as error:
            raise KnowledgeRAGError() from error

    def index_pdf(
        self,
        *,
        file_path: str | Path,
        knowledge_id: str,
    ) -> dict[str, Any]:
        resolved_path = _pdf_path(file_path)
        resolved_id = _knowledge_id(
            knowledge_id
        )

        try:
            result = self._service.add_pdf(
                file_path=resolved_path,
                chat_id=(
                    KNOWLEDGE_INTERNAL_SCOPE_ID
                ),
                document_id=resolved_id,
            )
        except Exception as error:
            raise KnowledgeRAGError() from error

        if not isinstance(result, dict):
            raise KnowledgeRAGError()

        try:
            pages = _nonnegative_integer(
                result["pages"]
            )
            chunks = _nonnegative_integer(
                result["chunks"]
            )
            filename = _pdf_filename(
                result.get(
                    "filename",
                    resolved_path.name,
                )
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            KnowledgeRAGError,
        ) as error:
            raise KnowledgeRAGError() from error

        return {
            "knowledge_id": resolved_id,
            "filename": filename,
            "pages": pages,
            "chunks": chunks,
        }

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
            raise KnowledgeRAGError()

        selected: list[str] = []
        seen: set[str] = set()

        for value in document_ids:
            candidate = _knowledge_id(
                value
            )

            if candidate in seen:
                continue

            seen.add(candidate)
            selected.append(candidate)

            if len(selected) > 200:
                raise KnowledgeRAGError()

        return selected

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filenames:
        Sequence[str] | None = None,
        document_ids:
        Sequence[str] | None = None,
    ) -> dict[str, Any]:
        resolved_query = _query(query)
        resolved_limit = _search_limit(limit)
        resolved_filenames = (
            _filename_filters(
                filenames
            )
        )
        resolved_document_ids = (
            self._normalize_document_ids(
                document_ids
            )
        )

        if (
            document_ids is not None
            and not resolved_document_ids
        ):
            return {
                "context": "",
                "sources": [],
            }

        search_kwargs = {
            "query": resolved_query,
            "limit": resolved_limit,
            "chat_id": (
                KNOWLEDGE_INTERNAL_SCOPE_ID
            ),
            "filenames": (
                resolved_filenames
            ),
        }

        if resolved_document_ids is not None:
            search_kwargs[
                "document_ids"
            ] = resolved_document_ids

        try:
            result = self._service.search(
                **search_kwargs
            )
        except Exception as error:
            raise KnowledgeRAGError() from error

        if not isinstance(result, dict):
            raise KnowledgeRAGError()

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
            raise KnowledgeRAGError()

        safe_sources = []

        for source in sources:
            if not isinstance(source, dict):
                raise KnowledgeRAGError()

            try:
                filename = _pdf_filename(
                    source.get(
                        "filename",
                        source.get(
                            "title",
                            "",
                        ),
                    )
                )
                page = source.get(
                    "page",
                )
                document_id = (
                    source.get(
                        "document_id"
                    )
                )

                safe_source = {
                    "type": "pdf",
                    "title": filename,
                    "filename": filename,
                    "page": page,
                }

                if document_id is not None:
                    safe_source[
                        "knowledge_id"
                    ] = _knowledge_id(
                        document_id
                    )

                safe_sources.append(
                    safe_source
                )
            except KnowledgeRAGError as error:
                raise KnowledgeRAGError() from error

        return {
            "context": context,
            "sources": safe_sources,
        }

    def delete_document(
        self,
        *,
        knowledge_id: str,
        filename: str,
    ) -> dict[str, Any]:
        resolved_id = _knowledge_id(
            knowledge_id
        )
        resolved_filename = (
            _pdf_filename(filename)
        )

        try:
            result = (
                self._service
                .delete_document(
                    document_id=resolved_id,
                    filename=(
                        resolved_filename
                    ),
                    chat_id=(
                        KNOWLEDGE_INTERNAL_SCOPE_ID
                    ),
                )
            )
        except Exception as error:
            raise KnowledgeRAGError() from error

        if not isinstance(result, dict):
            raise KnowledgeRAGError()

        try:
            deleted_chunks = (
                _nonnegative_integer(
                    result.get(
                        "deleted_chunks",
                        0,
                    )
                )
            )
            remaining_chunks = (
                _nonnegative_integer(
                    result.get(
                        "remaining_chunks",
                        0,
                    )
                )
            )
        except KnowledgeRAGError as error:
            raise KnowledgeRAGError() from error

        return {
            "knowledge_id": resolved_id,
            "filename": resolved_filename,
            "deleted_chunks": (
                deleted_chunks
            ),
            "remaining_chunks": (
                remaining_chunks
            ),
        }
