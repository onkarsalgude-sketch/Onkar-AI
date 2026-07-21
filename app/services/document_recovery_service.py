"""Discovery foundation for stuck document recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_object_service import (
    delete_document_object,
    materialize_pdf_bytes,
    read_document_bytes,
)
from app.services.document_service import (
    delete_document_record,
    get_document,
    list_documents_by_statuses,
    mark_document_failed,
    mark_document_ready,
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


@dataclass(frozen=True)
class DocumentRecoveryResult:
    document_id: str
    chat_id: int
    filename: str
    original_status: str
    outcome: str
    error: str | None = None


@dataclass(frozen=True)
class DocumentRecoveryRun:
    scan: DocumentRecoveryScan
    results: tuple[
        DocumentRecoveryResult,
        ...,
    ]

    @property
    def processing_recovered_count(
        self,
    ) -> int:
        return sum(
            result.outcome
            == "processing_recovered"
            for result in self.results
        )

    @property
    def deleting_completed_count(
        self,
    ) -> int:
        return sum(
            result.outcome
            == "deletion_completed"
            for result in self.results
        )

    @property
    def failure_count(self) -> int:
        return sum(
            result.outcome in {
                "processing_retry_failed",
                "processing_failed_missing_object",
                "deletion_retry_failed",
            }
            for result in self.results
        )

    @property
    def skipped_count(self) -> int:
        return sum(
            result.outcome in {
                "metadata_missing",
                "skipped_changed",
            }
            for result in self.results
        )


def _candidate_matches_document(
    candidate: DocumentRecoveryCandidate,
    document: dict,
) -> bool:
    status = str(
        document.get(
            "status",
            "",
        )
    ).strip().casefold()

    if status != candidate.status:
        return False

    current_updated_at = (
        _parse_document_timestamp(
            document.get(
                "updated_at"
            )
        )
    )

    candidate_updated_at = (
        _parse_document_timestamp(
            candidate.updated_at
        )
    )

    if (
        current_updated_at is None
        or candidate_updated_at is None
    ):
        return False

    return (
        current_updated_at
        == candidate_updated_at
    )


def _error_message(
    error: BaseException,
) -> str:
    message = str(error).strip()

    if message:
        return (
            f"{type(error).__name__}: "
            f"{message}"
        )

    return type(error).__name__


def _recover_processing_document(
    candidate: DocumentRecoveryCandidate,
    document: dict,
    *,
    rag: Any,
    read_document_bytes_fn: Callable = (
        read_document_bytes
    ),
    materialize_pdf_bytes_fn: Callable = (
        materialize_pdf_bytes
    ),
    mark_document_ready_fn: Callable = (
        mark_document_ready
    ),
    mark_document_failed_fn: Callable = (
        mark_document_failed
    ),
) -> DocumentRecoveryResult:
    try:
        document_bytes = (
            read_document_bytes_fn(
                document
            )
        )

        with materialize_pdf_bytes_fn(
            document_bytes,
            candidate.filename,
        ) as temporary_path:
            indexed = rag.add_pdf(
                file_path=temporary_path,
                chat_id=candidate.chat_id,
                document_id=(
                    candidate.document_id
                ),
            )

        page_count = int(
            indexed.get(
                "pages",
                0,
            )
            or 0
        )

        chunk_count = int(
            indexed.get(
                "chunks",
                0,
            )
            or 0
        )

        if page_count <= 0 or chunk_count <= 0:
            raise RuntimeError(
                "Recovered document produced "
                "no readable vector chunks."
            )

        ready_document = (
            mark_document_ready_fn(
                document_id=(
                    candidate.document_id
                ),
                chat_id=candidate.chat_id,
                page_count=page_count,
                chunk_count=chunk_count,
            )
        )

        if ready_document is None:
            raise RuntimeError(
                "Recovered document ready state "
                "was not saved."
            )

        return DocumentRecoveryResult(
            document_id=(
                candidate.document_id
            ),
            chat_id=candidate.chat_id,
            filename=candidate.filename,
            original_status=(
                candidate.status
            ),
            outcome="processing_recovered",
        )
    except Exception as error:
        if (
            type(error).__name__
            == "DocumentNotFoundError"
        ):
            try:
                mark_document_failed_fn(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                )
            except Exception as mark_error:
                return DocumentRecoveryResult(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                    filename=(
                        candidate.filename
                    ),
                    original_status=(
                        candidate.status
                    ),
                    outcome=(
                        "processing_retry_failed"
                    ),
                    error=(
                        _error_message(error)
                        + "; failed-state update: "
                        + _error_message(
                            mark_error
                        )
                    ),
                )

            return DocumentRecoveryResult(
                document_id=(
                    candidate.document_id
                ),
                chat_id=candidate.chat_id,
                filename=candidate.filename,
                original_status=(
                    candidate.status
                ),
                outcome=(
                    "processing_failed_missing_object"
                ),
                error=_error_message(
                    error
                ),
            )

        return DocumentRecoveryResult(
            document_id=(
                candidate.document_id
            ),
            chat_id=candidate.chat_id,
            filename=candidate.filename,
            original_status=(
                candidate.status
            ),
            outcome=(
                "processing_retry_failed"
            ),
            error=_error_message(
                error
            ),
        )


def _recover_deleting_document(
    candidate: DocumentRecoveryCandidate,
    document: dict,
    *,
    rag: Any,
    delete_document_object_fn: Callable = (
        delete_document_object
    ),
    delete_document_record_fn: Callable = (
        delete_document_record
    ),
    get_document_fn: Callable = (
        get_document
    ),
) -> DocumentRecoveryResult:
    try:
        delete_document_object_fn(
            document
        )

        vector_result = (
            rag.delete_document(
                document_id=(
                    candidate.document_id
                ),
                filename=(
                    candidate.filename
                ),
                chat_id=(
                    candidate.chat_id
                ),
            )
        )

        remaining_chunks = int(
            vector_result.get(
                "remaining_chunks",
                0,
            )
            or 0
        )

        if remaining_chunks != 0:
            raise RuntimeError(
                "Document vector cleanup "
                "left remaining chunks."
            )

        record_deleted = (
            delete_document_record_fn(
                document_id=(
                    candidate.document_id
                ),
                chat_id=candidate.chat_id,
            )
        )

        if not record_deleted:
            remaining_document = (
                get_document_fn(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                )
            )

            if remaining_document is not None:
                raise RuntimeError(
                    "Document metadata deletion "
                    "did not complete."
                )

        return DocumentRecoveryResult(
            document_id=(
                candidate.document_id
            ),
            chat_id=candidate.chat_id,
            filename=candidate.filename,
            original_status=(
                candidate.status
            ),
            outcome="deletion_completed",
        )
    except Exception as error:
        return DocumentRecoveryResult(
            document_id=(
                candidate.document_id
            ),
            chat_id=candidate.chat_id,
            filename=candidate.filename,
            original_status=(
                candidate.status
            ),
            outcome="deletion_retry_failed",
            error=_error_message(
                error
            ),
        )


def recover_stuck_documents(
    settings: DocumentRecoverySettings,
    *,
    rag: Any,
    now: datetime | None = None,
    list_documents_fn: Callable = (
        list_documents_by_statuses
    ),
    get_document_fn: Callable = (
        get_document
    ),
    read_document_bytes_fn: Callable = (
        read_document_bytes
    ),
    materialize_pdf_bytes_fn: Callable = (
        materialize_pdf_bytes
    ),
    delete_document_object_fn: Callable = (
        delete_document_object
    ),
    mark_document_ready_fn: Callable = (
        mark_document_ready
    ),
    mark_document_failed_fn: Callable = (
        mark_document_failed
    ),
    delete_document_record_fn: Callable = (
        delete_document_record
    ),
) -> DocumentRecoveryRun:
    scan = scan_stuck_documents(
        settings,
        now=now,
        list_documents_fn=(
            list_documents_fn
        ),
    )

    if not scan.enabled:
        return DocumentRecoveryRun(
            scan=scan,
            results=(),
        )

    results = []

    for candidate in scan.candidates:
        document = get_document_fn(
            document_id=(
                candidate.document_id
            ),
            chat_id=candidate.chat_id,
        )

        if document is None:
            results.append(
                DocumentRecoveryResult(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                    filename=(
                        candidate.filename
                    ),
                    original_status=(
                        candidate.status
                    ),
                    outcome="metadata_missing",
                )
            )

            continue

        if not _candidate_matches_document(
            candidate,
            document,
        ):
            results.append(
                DocumentRecoveryResult(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                    filename=(
                        candidate.filename
                    ),
                    original_status=(
                        candidate.status
                    ),
                    outcome="skipped_changed",
                )
            )

            continue

        if candidate.status == "processing":
            result = (
                _recover_processing_document(
                    candidate,
                    document,
                    rag=rag,
                    read_document_bytes_fn=(
                        read_document_bytes_fn
                    ),
                    materialize_pdf_bytes_fn=(
                        materialize_pdf_bytes_fn
                    ),
                    mark_document_ready_fn=(
                        mark_document_ready_fn
                    ),
                    mark_document_failed_fn=(
                        mark_document_failed_fn
                    ),
                )
            )
        elif candidate.status == "deleting":
            result = (
                _recover_deleting_document(
                    candidate,
                    document,
                    rag=rag,
                    delete_document_object_fn=(
                        delete_document_object_fn
                    ),
                    delete_document_record_fn=(
                        delete_document_record_fn
                    ),
                    get_document_fn=(
                        get_document_fn
                    ),
                )
            )
        else:
            result = (
                DocumentRecoveryResult(
                    document_id=(
                        candidate.document_id
                    ),
                    chat_id=(
                        candidate.chat_id
                    ),
                    filename=(
                        candidate.filename
                    ),
                    original_status=(
                        candidate.status
                    ),
                    outcome="skipped_changed",
                )
            )

        results.append(result)

    return DocumentRecoveryRun(
        scan=scan,
        results=tuple(results),
    )
