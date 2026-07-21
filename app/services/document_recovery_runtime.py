"""Non-fatal startup runtime for document recovery."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable

from app.config.document_recovery import (
    DocumentRecoverySettings,
    load_document_recovery_settings,
)
from app.services.document_recovery_service import (
    recover_stuck_documents,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentRecoveryStartupReport:
    status: str
    enabled: bool
    total_examined: int
    candidate_count: int
    processing_recovered_count: int
    deleting_completed_count: int
    failure_count: int
    skipped_count: int
    recent_count: int
    invalid_timestamp_count: int
    deferred_count: int
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _exception_message(
    error: BaseException,
) -> str:
    message = str(error).strip()

    if message:
        return (
            f"{type(error).__name__}: "
            f"{message}"
        )

    return type(error).__name__


def run_document_recovery_startup(
    *,
    rag: Any,
    settings: DocumentRecoverySettings | None = None,
    now: datetime | None = None,
    recover_fn: Callable = recover_stuck_documents,
    logger: logging.Logger | None = None,
) -> DocumentRecoveryStartupReport:
    resolved_logger = (
        LOGGER
        if logger is None
        else logger
    )

    resolved_settings = (
        load_document_recovery_settings()
        if settings is None
        else settings
    )

    if not resolved_settings.enabled:
        report = DocumentRecoveryStartupReport(
            status="disabled",
            enabled=False,
            total_examined=0,
            candidate_count=0,
            processing_recovered_count=0,
            deleting_completed_count=0,
            failure_count=0,
            skipped_count=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
        )

        resolved_logger.info(
            "Document recovery startup is disabled."
        )

        return report

    try:
        run = recover_fn(
            resolved_settings,
            rag=rag,
            now=now,
        )
    except Exception as error:
        resolved_logger.exception(
            "Document recovery startup failed."
        )

        return DocumentRecoveryStartupReport(
            status="failed",
            enabled=True,
            total_examined=0,
            candidate_count=0,
            processing_recovered_count=0,
            deleting_completed_count=0,
            failure_count=1,
            skipped_count=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
            error=_exception_message(error),
        )

    status = (
        "completed_with_failures"
        if run.failure_count > 0
        else "completed"
    )

    report = DocumentRecoveryStartupReport(
        status=status,
        enabled=True,
        total_examined=(
            run.scan.total_examined
        ),
        candidate_count=(
            run.scan.candidate_count
        ),
        processing_recovered_count=(
            run.processing_recovered_count
        ),
        deleting_completed_count=(
            run.deleting_completed_count
        ),
        failure_count=run.failure_count,
        skipped_count=run.skipped_count,
        recent_count=(
            run.scan.recent_count
        ),
        invalid_timestamp_count=(
            run.scan.invalid_timestamp_count
        ),
        deferred_count=(
            run.scan.deferred_count
        ),
    )

    log_arguments = (
        report.status,
        report.total_examined,
        report.candidate_count,
        report.processing_recovered_count,
        report.deleting_completed_count,
        report.failure_count,
        report.skipped_count,
        report.deferred_count,
    )

    if report.failure_count:
        resolved_logger.warning(
            (
                "Document recovery startup finished "
                "with status=%s examined=%s "
                "candidates=%s processing=%s "
                "deleting=%s failures=%s skipped=%s "
                "deferred=%s"
            ),
            *log_arguments,
        )
    else:
        resolved_logger.info(
            (
                "Document recovery startup finished "
                "with status=%s examined=%s "
                "candidates=%s processing=%s "
                "deleting=%s failures=%s skipped=%s "
                "deferred=%s"
            ),
            *log_arguments,
        )

    return report
