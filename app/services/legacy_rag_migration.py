"""Safe migration of legacy Chroma embeddings into PostgreSQL pgvector."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.database.rag_schema import (
    RAG_TABLE_NAME,
)


LEGACY_ID_PATTERN = re.compile(
    r"""
    ^
    (?P<filename>.+?\.pdf)
    -
    (?P<chunk_index>\d+)
    (?:
        -
        (?P<suffix>
            [0-9a-fA-F]{8}
            -
            [0-9a-fA-F]{4}
            -
            [0-9a-fA-F]{4}
            -
            [0-9a-fA-F]{4}
            -
            [0-9a-fA-F]{12}
        )
    )?
    $
    """,
    flags=re.VERBOSE,
)


class LegacyRAGMigrationError(
    RuntimeError
):
    """Raised without exposing document content or credentials."""

    def __init__(self):
        super().__init__(
            "Legacy RAG migration failed."
        )


@dataclass(frozen=True)
class LegacyFingerprint:
    filename: str
    page: int
    chunk_index: int
    content: str
    embedding: tuple[float, ...]
    content_hash: str
    embedding_hash: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LegacyRAGTarget:
    chat_id: int
    document_id: str
    filename: str
    file_hash: str
    page_count: int
    chunk_count: int
    chunk_id: str
    source: LegacyFingerprint


@dataclass(frozen=True)
class UnmatchedDocument:
    chat_id: int
    document_id: str
    filename: str
    reason: str


@dataclass(frozen=True)
class LegacyRAGPlan:
    targets: tuple[
        LegacyRAGTarget,
        ...,
    ]

    unmatched_documents: tuple[
        UnmatchedDocument,
        ...,
    ]

    issues: tuple[
        str,
        ...,
    ]

    source_record_count: int
    distinct_source_fingerprints: int
    ignored_source_duplicates: int

    @property
    def can_execute(self) -> bool:
        return (
            bool(self.targets)
            and not self.issues
        )


@dataclass(frozen=True)
class LegacyRAGMigrationReport:
    migrated_documents: int
    migrated_chunks: int
    ignored_source_duplicates: int
    unmatched_documents: int


def _safe_filename(
    value: object,
) -> str:
    candidate = str(
        value or ""
    ).strip()

    if (
        not candidate
        or len(candidate) > 255
        or Path(candidate).name
        != candidate
        or Path(candidate)
        .suffix.casefold()
        != ".pdf"
    ):
        raise LegacyRAGMigrationError()

    return candidate


def _positive_integer(
    value: object,
) -> int:
    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            LegacyRAGMigrationError()
        ) from error

    if parsed <= 0:
        raise LegacyRAGMigrationError()

    return parsed


def _non_negative_integer(
    value: object,
) -> int:
    try:
        parsed = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            LegacyRAGMigrationError()
        ) from error

    if parsed < 0:
        raise LegacyRAGMigrationError()

    return parsed


def _text_hash(
    value: object,
) -> str:
    return hashlib.sha256(
        str(value or "").encode(
            "utf-8"
        )
    ).hexdigest()


def _normalize_embedding(
    embedding,
    *,
    dimension: int,
) -> tuple[float, ...]:
    if embedding is None:
        raise LegacyRAGMigrationError()

    try:
        values = tuple(
            float(value)
            for value in embedding
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        raise (
            LegacyRAGMigrationError()
        ) from error

    if (
        len(values) != dimension
        or not all(
            math.isfinite(value)
            for value in values
        )
    ):
        raise LegacyRAGMigrationError()

    return values


def _embedding_hash(
    embedding:
    Sequence[float],
) -> str:
    normalized = [
        format(
            float(value),
            ".17g",
        )
        for value in embedding
    ]

    payload = json.dumps(
        normalized,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def _vector_literal(
    embedding:
    Sequence[float],
) -> str:
    return (
        "["
        + ",".join(
            format(
                float(value),
                ".17g",
            )
            for value in embedding
        )
        + "]"
    )


def _close_safely(
    resource,
) -> None:
    close = getattr(
        resource,
        "close",
        None,
    )

    if callable(close):
        close()


def _load_database_documents(
    connection,
) -> list[dict[str, Any]]:
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                document_id,
                chat_id,
                filename,
                file_hash,
                page_count,
                chunk_count,
                status
            FROM documents
            ORDER BY
                lower(filename),
                chat_id,
                document_id
            """
        )

        rows = cursor.fetchall()

    finally:
        _close_safely(
            cursor
        )

    documents = []

    for row in rows:
        documents.append(
            {
                "document_id": str(
                    row[0]
                ),
                "chat_id": int(
                    row[1]
                ),
                "filename": (
                    _safe_filename(
                        row[2]
                    )
                ),
                "file_hash": str(
                    row[3] or ""
                ).strip().casefold(),
                "page_count": int(
                    row[4] or 0
                ),
                "chunk_count": int(
                    row[5] or 0
                ),
                "status": str(
                    row[6] or ""
                ).strip().casefold(),
            }
        )

    return documents


def _load_legacy_records(
    collection,
    *,
    embedding_dimension: int,
) -> list[dict[str, Any]]:
    result = collection.get(
        include=[
            "documents",
            "metadatas",
            "embeddings",
        ]
    )

    ids = result.get(
        "ids",
        [],
    )

    documents = (
        result.get(
            "documents",
            [],
        )
        or []
    )

    metadatas = (
        result.get(
            "metadatas",
            [],
        )
        or []
    )

    embeddings = result.get(
        "embeddings"
    )

    if embeddings is None:
        raise LegacyRAGMigrationError()

    records = []

    for index, raw_chunk_id in enumerate(
        ids
    ):
        chunk_id = str(
            raw_chunk_id
        )

        parsed = (
            LEGACY_ID_PATTERN
            .fullmatch(chunk_id)
        )

        if parsed is None:
            raise LegacyRAGMigrationError()

        parsed_values = (
            parsed.groupdict()
        )

        metadata = (
            metadatas[index]
            if (
                index
                < len(metadatas)
                and metadatas[index]
            )
            else {}
        )

        content = str(
            documents[index]
            if index < len(documents)
            else ""
        ).strip()

        if not content:
            raise LegacyRAGMigrationError()

        filename = _safe_filename(
            metadata.get(
                "filename"
            )
            or parsed_values[
                "filename"
            ]
        )

        raw_chunk_index = (
            metadata.get(
                "chunk_index"
            )
        )

        if raw_chunk_index is None:
            raw_chunk_index = (
                parsed_values[
                    "chunk_index"
                ]
            )

        chunk_index = (
            _non_negative_integer(
                raw_chunk_index
            )
        )

        page = _positive_integer(
            metadata.get(
                "page",
                1,
            )
            or 1
        )

        embedding = (
            _normalize_embedding(
                embeddings[index],
                dimension=(
                    embedding_dimension
                ),
            )
        )

        records.append(
            {
                "source_id": chunk_id,
                "filename": filename,
                "page": page,
                "chunk_index": (
                    chunk_index
                ),
                "content": content,
                "embedding": embedding,
                "content_hash": (
                    _text_hash(content)
                ),
                "embedding_hash": (
                    _embedding_hash(
                        embedding
                    )
                ),
            }
        )

    return records


def build_legacy_rag_plan(
    source_connection,
    collection,
    *,
    embedding_dimension: int = 384,
) -> LegacyRAGPlan:
    documents = (
        _load_database_documents(
            source_connection
        )
    )

    legacy_records = (
        _load_legacy_records(
            collection,
            embedding_dimension=(
                embedding_dimension
            ),
        )
    )

    database_groups = defaultdict(
        list
    )

    for document in documents:
        database_groups[
            document[
                "filename"
            ].casefold()
        ].append(
            document
        )

    fingerprint_groups = defaultdict(
        list
    )

    for record in legacy_records:
        key = (
            record[
                "filename"
            ].casefold(),
            record["page"],
            record[
                "chunk_index"
            ],
            record[
                "content_hash"
            ],
            record[
                "embedding_hash"
            ],
        )

        fingerprint_groups[
            key
        ].append(
            record
        )

    source_groups_by_filename = (
        defaultdict(list)
    )

    for key, records in (
        fingerprint_groups.items()
    ):
        source_groups_by_filename[
            key[0]
        ].append(
            (
                key,
                records,
            )
        )

    targets = []
    issues = []
    ignored_duplicates = 0

    for (
        filename_key,
        source_groups,
    ) in sorted(
        source_groups_by_filename.items()
    ):
        matching_documents = (
            database_groups.get(
                filename_key,
                [],
            )
        )

        if not matching_documents:
            issues.append(
                "A legacy filename has "
                "no matching database document."
            )
            continue

        if len(source_groups) != 1:
            issues.append(
                "A legacy filename has "
                "multiple distinct fingerprints."
            )
            continue

        (
            fingerprint_key,
            duplicate_records,
        ) = source_groups[0]

        (
            _,
            page,
            chunk_index,
            content_hash,
            embedding_hash,
        ) = fingerprint_key

        canonical = sorted(
            duplicate_records,
            key=lambda item: (
                item["source_id"]
            ),
        )[0]

        source = LegacyFingerprint(
            filename=canonical[
                "filename"
            ],
            page=page,
            chunk_index=(
                chunk_index
            ),
            content=canonical[
                "content"
            ],
            embedding=canonical[
                "embedding"
            ],
            content_hash=(
                content_hash
            ),
            embedding_hash=(
                embedding_hash
            ),
            source_ids=tuple(
                sorted(
                    item["source_id"]
                    for item
                    in duplicate_records
                )
            ),
        )

        ignored_duplicates += max(
            len(
                duplicate_records
            )
            - 1,
            0,
        )

        unique_file_hashes = {
            item["file_hash"]
            for item
            in matching_documents
            if item["file_hash"]
        }

        if len(
            unique_file_hashes
        ) != 1:
            issues.append(
                "Matching documents do not "
                "share one file hash."
            )
            continue

        for document in (
            matching_documents
        ):
            if (
                document["status"]
                != "ready"
                or document[
                    "page_count"
                ]
                < page
                or document[
                    "chunk_count"
                ]
                <= chunk_index
            ):
                issues.append(
                    "Matching document metadata "
                    "is incompatible."
                )
                continue

            chunk_id = (
                f"chat-"
                f"{document['chat_id']}-"
                f"{document['document_id']}-"
                f"page-{page}-"
                f"chunk-{chunk_index}"
            )

            targets.append(
                LegacyRAGTarget(
                    chat_id=document[
                        "chat_id"
                    ],
                    document_id=document[
                        "document_id"
                    ],
                    filename=document[
                        "filename"
                    ],
                    file_hash=document[
                        "file_hash"
                    ],
                    page_count=document[
                        "page_count"
                    ],
                    chunk_count=document[
                        "chunk_count"
                    ],
                    chunk_id=chunk_id,
                    source=source,
                )
            )

    matched_filename_keys = set(
        source_groups_by_filename
    )

    unmatched_documents = []

    for document in documents:
        if (
            document[
                "filename"
            ].casefold()
            in matched_filename_keys
        ):
            continue

        unmatched_documents.append(
            UnmatchedDocument(
                chat_id=document[
                    "chat_id"
                ],
                document_id=document[
                    "document_id"
                ],
                filename=document[
                    "filename"
                ],
                reason=(
                    "No matching legacy "
                    "Chroma fingerprint exists."
                ),
            )
        )

    target_ids = [
        target.chunk_id
        for target in targets
    ]

    if len(target_ids) != len(
        set(target_ids)
    ):
        issues.append(
            "Duplicate target chunk IDs "
            "were generated."
        )

    return LegacyRAGPlan(
        targets=tuple(
            sorted(
                targets,
                key=lambda item: (
                    item.chat_id,
                    item.filename
                    .casefold(),
                    item.chunk_id,
                ),
            )
        ),
        unmatched_documents=tuple(
            unmatched_documents
        ),
        issues=tuple(
            issues
        ),
        source_record_count=len(
            legacy_records
        ),
        distinct_source_fingerprints=len(
            fingerprint_groups
        ),
        ignored_source_duplicates=(
            ignored_duplicates
        ),
    )


def _verify_target_document(
    cursor,
    target: LegacyRAGTarget,
) -> None:
    cursor.execute(
        """
        SELECT
            document_id,
            chat_id,
            filename,
            file_hash,
            page_count,
            chunk_count,
            status
        FROM documents
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            target.document_id,
            target.chat_id,
        ),
    )

    row = cursor.fetchone()

    if row is None:
        raise LegacyRAGMigrationError()

    if (
        str(row[0])
        != target.document_id
        or int(row[1])
        != target.chat_id
        or str(row[2])
        .strip()
        .casefold()
        != target.filename
        .casefold()
        or str(row[3] or "")
        .strip()
        .casefold()
        != target.file_hash
        or int(row[4] or 0)
        != target.page_count
        or int(row[5] or 0)
        != target.chunk_count
        or str(row[6] or "")
        .strip()
        .casefold()
        != "ready"
    ):
        raise LegacyRAGMigrationError()


def execute_legacy_rag_migration(
    plan: LegacyRAGPlan,
    target_connection,
    *,
    collection_name: str,
) -> LegacyRAGMigrationReport:
    if not plan.can_execute:
        raise LegacyRAGMigrationError()

    resolved_collection_name = str(
        collection_name or ""
    ).strip().casefold()

    if not re.fullmatch(
        r"[a-z][a-z0-9_]{2,62}",
        resolved_collection_name,
    ):
        raise LegacyRAGMigrationError()

    cursor = target_connection.cursor()

    try:
        for target in plan.targets:
            _verify_target_document(
                cursor,
                target,
            )

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        for target in plan.targets:
            cursor.execute(
                f"""
                DELETE FROM public.{RAG_TABLE_NAME}
                WHERE collection_name = ?
                  AND chat_id = ?
                  AND document_id = ?
                """,
                (
                    resolved_collection_name,
                    target.chat_id,
                    target.document_id,
                ),
            )

            cursor.execute(
                f"""
                INSERT INTO public.{RAG_TABLE_NAME} (
                    chunk_id,
                    collection_name,
                    chat_id,
                    document_id,
                    filename,
                    page,
                    chunk_index,
                    content,
                    embedding,
                    embedding_model,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, CAST(? AS vector),
                    'default', ?
                )
                """,
                (
                    target.chunk_id,
                    resolved_collection_name,
                    target.chat_id,
                    target.document_id,
                    target.filename,
                    target.source.page,
                    target.source.chunk_index,
                    target.source.content,
                    _vector_literal(
                        target.source.embedding
                    ),
                    created_at,
                ),
            )

        target_connection.commit()

    except Exception as error:
        try:
            target_connection.rollback()
        except Exception:
            pass

        if isinstance(
            error,
            LegacyRAGMigrationError,
        ):
            raise

        raise (
            LegacyRAGMigrationError()
        ) from error

    finally:
        _close_safely(
            cursor
        )

    return LegacyRAGMigrationReport(
        migrated_documents=len(
            plan.targets
        ),
        migrated_chunks=len(
            plan.targets
        ),
        ignored_source_duplicates=(
            plan
            .ignored_source_duplicates
        ),
        unmatched_documents=len(
            plan.unmatched_documents
        ),
    )
