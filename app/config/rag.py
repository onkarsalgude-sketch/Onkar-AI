"""Fail-closed configuration for local Chroma and PostgreSQL pgvector RAG."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.config.database import (
    DatabaseConfigurationError,
    DatabaseSettings,
    load_database_settings,
)


DEFAULT_EMBEDDING_DIMENSION = 384
DEFAULT_COLLECTION_NAME = "pdf_documents"

_COLLECTION_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{2,62}$"
)


class RAGConfigurationError(
    RuntimeError
):
    """Raised without exposing configuration secrets."""

    def __init__(self):
        super().__init__(
            "RAG configuration is invalid."
        )


@dataclass(frozen=True)
class RAGSettings:
    backend: str
    require_persistence: bool
    embedding_dimension: int
    collection_name: str
    chroma_path: Path
    database: DatabaseSettings

    @property
    def is_chroma(self) -> bool:
        return self.backend == "chroma"

    @property
    def is_pgvector(self) -> bool:
        return self.backend == "pgvector"

    @property
    def safe_target(self) -> str:
        """Return a credential-free target for logs."""

        if self.is_pgvector:
            return (
                f"{self.database.safe_target}"
                f"#rag={self.collection_name}"
            )

        resolved_path = (
            self.chroma_path
            .expanduser()
            .resolve(
                strict=False
            )
        )

        return (
            f"chroma:///{resolved_path}"
        )


def _parse_bool(
    value: object,
) -> bool:
    normalized = str(
        value
    ).strip().casefold()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "",
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise RAGConfigurationError()


def _parse_dimension(
    value: object,
) -> int:
    try:
        dimension = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            RAGConfigurationError()
        ) from error

    if not (
        1
        <= dimension
        <= 4096
    ):
        raise RAGConfigurationError()

    return dimension


def _parse_collection_name(
    value: object,
) -> str:
    candidate = str(
        value
    ).strip().casefold()

    if not (
        _COLLECTION_NAME_PATTERN
        .fullmatch(candidate)
    ):
        raise RAGConfigurationError()

    return candidate


def load_rag_settings(
    environ: Mapping[str, str]
    | None = None,
    *,
    default_chroma_path:
    str | Path | None = None,
) -> RAGSettings:
    """Select Chroma locally and pgvector for PostgreSQL by default."""

    source = (
        os.environ
        if environ is None
        else environ
    )

    try:
        database = (
            load_database_settings(
                source
            )
        )
    except (
        DatabaseConfigurationError
    ) as error:
        raise (
            RAGConfigurationError()
        ) from error

    raw_backend = str(
        source.get(
            "RAG_BACKEND",
            "",
        )
    ).strip().casefold()

    if raw_backend:
        if raw_backend not in {
            "chroma",
            "pgvector",
        }:
            raise (
                RAGConfigurationError()
            )

        backend = raw_backend

    else:
        backend = (
            "pgvector"
            if database.is_postgresql
            else "chroma"
        )

    rag_requires_persistence = (
        _parse_bool(
            source.get(
                "RAG_REQUIRE_PERSISTENCE",
                "false",
            )
        )
    )

    require_persistence = (
        database.require_persistence
        or rag_requires_persistence
    )

    embedding_dimension = (
        _parse_dimension(
            source.get(
                "RAG_EMBEDDING_DIMENSION",
                str(
                    DEFAULT_EMBEDDING_DIMENSION
                ),
            )
        )
    )

    collection_name = (
        _parse_collection_name(
            source.get(
                "RAG_COLLECTION_NAME",
                DEFAULT_COLLECTION_NAME,
            )
        )
    )

    raw_chroma_path = str(
        source.get(
            "VECTOR_DB_DIR",
            "",
        )
    ).strip()

    fallback_chroma_path = (
        Path(default_chroma_path)
        if default_chroma_path
        is not None
        else (
            Path(__file__)
            .resolve()
            .parents[2]
            / "storage"
            / "vector_db"
        )
    )

    chroma_path = (
        Path(
            raw_chroma_path
        ).expanduser()
        if raw_chroma_path
        else fallback_chroma_path
    )

    if (
        backend == "pgvector"
        and not database.is_postgresql
    ):
        raise RAGConfigurationError()

    if (
        require_persistence
        and backend != "pgvector"
    ):
        raise RAGConfigurationError()

    return RAGSettings(
        backend=backend,
        require_persistence=(
            require_persistence
        ),
        embedding_dimension=(
            embedding_dimension
        ),
        collection_name=(
            collection_name
        ),
        chroma_path=chroma_path,
        database=database,
    )
