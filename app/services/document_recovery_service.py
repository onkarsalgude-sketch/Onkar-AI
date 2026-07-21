"""Discovery foundation for stuck document recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_service import (
    list_documents_by_statuses,
)


RECOVERABLE_DOCUMENT_STATUSES = (
    "processing",
    "deleting",
)


@dataclass(frozen=True)
class DocumentRecoveryCandidate:
    document_id: str
    chat_id: int
    filename: str
    status: str
    updated_at: str
    age_seconds: int


@dataclass(frozen=True)
class DocumentRecoveryScan:
    enabled: bool
    total_examined: int
    recent_count: int
    invalid_timestamp_count: int
    deferred_count: int
    candidates: tuple[
        DocumentRecoveryCandidate,
        ...,
    ]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)


def _parse_document_timestamp(
    value: object,
) -> datetime | None:
    normalized = str(
        value or ""
    ).strip()

    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _utc_datetime(
    value: datetime | None,
) -> datetime:
    resolved = (
        datetime.now(timezone.utc)
        if value is None
        else value
    )

    if resolved.tzinfo is None:
        resolved = resolved.replace(
            tzinfo=timezone.utc
        )

    return resolved.astimezone(
        timezone.utc
    )


def scan_stuck_documents(
    settings: DocumentRecoverySettings,
    *,
    now: datetime | None = None,
    list_documents_fn: Callable[
        [tuple[str, ...]],
        list[dict],
    ] = list_documents_by_statuses,
) -> DocumentRecoveryScan:
    if not settings.enabled:
        return DocumentRecoveryScan(
            enabled=False,
            total_examined=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
            candidates=(),
        )

    current_time = _utc_datetime(
        now
    )

    documents = list_documents_fn(
        RECOVERABLE_DOCUMENT_STATUSES
    )

    stale_candidates = []
    recent_count = 0
    invalid_timestamp_count = 0

    for document in documents:
        status = str(
            document.get(
                "status",
                "",
            )
        ).strip().casefold()

        if (
            status
            not in RECOVERABLE_DOCUMENT_STATUSES
        ):
            continue

        updated_at = (
            _parse_document_timestamp(
                document.get(
                    "updated_at"
                )
            )
        )

        if updated_at is None:
            invalid_timestamp_count += 1
            continue

        age_seconds = max(
            0,
            int(
                (
                    current_time
                    - updated_at
                ).total_seconds()
            ),
        )

        if (
            age_seconds
            < settings.stale_after_seconds
        ):
            recent_count += 1
            continue

        stale_candidates.append(
            (
                updated_at,
                DocumentRecoveryCandidate(
                    document_id=str(
                        document[
                            "document_id"
                        ]
                    ),
                    chat_id=int(
                        document["chat_id"]
                    ),
                    filename=str(
                        document["filename"]
                    ),
                    status=status,
                    updated_at=(
                        updated_at.isoformat()
                    ),
                    age_seconds=(
                        age_seconds
                    ),
                ),
            )
        )

    stale_candidates.sort(
        key=lambda item: (
            item[0],
            item[1].document_id,
        )
    )

    deferred_count = max(
        0,
        len(stale_candidates)
        - settings.batch_size,
    )

    selected = stale_candidates[
        :settings.batch_size
    ]

    return DocumentRecoveryScan(
        enabled=True,
        total_examined=len(documents),
        recent_count=recent_count,
        invalid_timestamp_count=(
            invalid_timestamp_count
        ),
        deferred_count=deferred_count,
        candidates=tuple(
            candidate
            for _, candidate in selected
        ),
    )
