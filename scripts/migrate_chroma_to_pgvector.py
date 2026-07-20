from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


import chromadb  # noqa: E402

from app.config.rag import (  # noqa: E402
    RAGConfigurationError,
    load_rag_settings,
)
from app.database.db import (  # noqa: E402
    get_runtime_connection,
)
from app.database.engine import (  # noqa: E402
    build_database_engine,
)
from app.database.rag_schema import (  # noqa: E402
    initialize_pgvector_schema,
)
from app.services.legacy_rag_migration import (  # noqa: E402
    LegacyRAGMigrationError,
    build_legacy_rag_plan,
    execute_legacy_rag_migration,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy Chroma "
            "embeddings into pgvector."
        )
    )

    parser.add_argument(
        "--source-sqlite-path",
        default=(
            "app/database/"
            "chat_history.db"
        ),
    )

    parser.add_argument(
        "--vector-root",
        default=(
            "storage/uploads/"
            "vector_db"
        ),
    )

    parser.add_argument(
        "--source-collection",
        default="documents",
    )

    mode = (
        parser
        .add_mutually_exclusive_group(
            required=True
        )
    )

    mode.add_argument(
        "--dry-run",
        action="store_true",
    )

    mode.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
    )

    return parser


def print_plan(
    plan,
) -> None:
    print(
        "\nLegacy RAG migration plan:"
    )

    print(
        "  source records:",
        plan.source_record_count,
    )

    print(
        "  distinct fingerprints:",
        plan.distinct_source_fingerprints,
    )

    print(
        "  recoverable targets:",
        len(plan.targets),
    )

    print(
        "  ignored duplicates:",
        plan.ignored_source_duplicates,
    )

    print(
        "  unmatched documents:",
        len(
            plan.unmatched_documents
        ),
    )

    print(
        "  blocking issues:",
        len(plan.issues),
    )

    for target in plan.targets:
        print(
            "  target:",
            {
                "chat_id": (
                    target.chat_id
                ),
                "document_id": (
                    target.document_id
                ),
                "filename": (
                    target.filename
                ),
                "chunk_id": (
                    target.chunk_id
                ),
                "content_hash_prefix": (
                    target.source
                    .content_hash[:12]
                ),
                "embedding_hash_prefix": (
                    target.source
                    .embedding_hash[:12]
                ),
            },
        )

    for document in (
        plan.unmatched_documents
    ):
        print(
            "  unmatched:",
            {
                "chat_id": (
                    document.chat_id
                ),
                "document_id": (
                    document.document_id
                ),
                "filename": (
                    document.filename
                ),
                "reason": (
                    document.reason
                ),
            },
        )

    for issue in plan.issues:
        print(
            "  issue:",
            issue,
        )


def main() -> int:
    arguments = (
        build_parser()
        .parse_args()
    )

    if (
        arguments.execute
        and not arguments.yes
    ):
        raise SystemExit(
            "--yes is required "
            "with --execute."
        )

    source_path = Path(
        arguments
        .source_sqlite_path
    ).expanduser().resolve(
        strict=False
    )

    vector_root = Path(
        arguments.vector_root
    ).expanduser().resolve(
        strict=False
    )

    if not source_path.is_file():
        raise SystemExit(
            "Source SQLite database "
            "was not found."
        )

    if not vector_root.is_dir():
        raise SystemExit(
            "Legacy Chroma directory "
            "was not found."
        )

    source_connection = (
        sqlite3.connect(
            source_path
        )
    )

    try:
        client = (
            chromadb
            .PersistentClient(
                path=str(
                    vector_root
                )
            )
        )

        collection = (
            client.get_collection(
                name=(
                    arguments
                    .source_collection
                )
            )
        )

        plan = (
            build_legacy_rag_plan(
                source_connection,
                collection,
            )
        )

    finally:
        source_connection.close()

    print_plan(
        plan
    )

    if arguments.dry_run:
        print(
            "\nDry run complete. "
            "No pgvector rows were changed."
        )

        return (
            0
            if plan.can_execute
            else 1
        )

    if not plan.can_execute:
        print(
            "\nMigration stopped because "
            "the plan contains issues.",
            file=sys.stderr,
        )

        return 1

    try:
        settings = (
            load_rag_settings()
        )

    except RAGConfigurationError:
        print(
            "\nMigration stopped because "
            "RAG configuration is invalid.",
            file=sys.stderr,
        )

        return 1

    if not settings.is_pgvector:
        print(
            "\nMigration stopped because "
            "pgvector is not selected.",
            file=sys.stderr,
        )

        return 1

    engine = (
        build_database_engine(
            settings.database
        )
    )

    try:
        initialize_pgvector_schema(
            engine,
            settings,
        )
    finally:
        engine.dispose()

    environment = dict(
        os.environ
    )

    target_connection = (
        get_runtime_connection(
            environ=environment
        )
    )

    try:
        report = (
            execute_legacy_rag_migration(
                plan,
                target_connection,
                collection_name=(
                    settings
                    .collection_name
                ),
            )
        )

    except LegacyRAGMigrationError:
        print(
            "\nLegacy RAG migration failed.",
            file=sys.stderr,
        )

        return 1

    finally:
        target_connection.close()

    print(
        "\nLegacy RAG migration: PASSED"
    )

    print(
        "  migrated documents:",
        report.migrated_documents,
    )

    print(
        "  migrated chunks:",
        report.migrated_chunks,
    )

    print(
        "  ignored duplicates:",
        report
        .ignored_source_duplicates,
    )

    print(
        "  unmatched documents:",
        report.unmatched_documents,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
