"""Startup initialization for local Chroma or PostgreSQL pgvector RAG."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.config.rag import (
    RAGConfigurationError,
    RAGSettings,
    load_rag_settings,
)
from app.database.engine import (
    build_database_engine,
)
from app.database.rag_schema import (
    RAGSchemaError,
    RAGSchemaReport,
    initialize_pgvector_schema,
)


class RAGRuntimeError(RuntimeError):
    """Raised without exposing database credentials."""

    def __init__(self):
        super().__init__(
            "RAG persistence initialization failed."
        )


@dataclass(frozen=True)
class RAGRuntime:
    settings: RAGSettings
    schema_report: RAGSchemaReport | None


def initialize_rag_runtime(
    environ: Mapping[str, str]
    | None = None,
    *,
    engine_builder: Callable[
        [Any],
        Any,
    ] = build_database_engine,
    schema_initializer: Callable[
        [Any, RAGSettings],
        RAGSchemaReport,
    ] = initialize_pgvector_schema,
) -> RAGRuntime:
    """Resolve the backend and initialize pgvector when required."""

    try:
        settings = load_rag_settings(
            environ
        )
    except RAGConfigurationError as error:
        raise RAGRuntimeError() from error

    if settings.is_chroma:
        return RAGRuntime(
            settings=settings,
            schema_report=None,
        )

    engine = None

    try:
        engine = engine_builder(
            settings.database
        )

        report = schema_initializer(
            engine,
            settings,
        )

        return RAGRuntime(
            settings=settings,
            schema_report=report,
        )

    except (
        RAGSchemaError,
        Exception,
    ) as error:
        raise RAGRuntimeError() from error

    finally:
        if engine is not None:
            dispose = getattr(
                engine,
                "dispose",
                None,
            )

            if callable(dispose):
                dispose()
