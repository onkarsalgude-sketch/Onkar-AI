"""Non-fatal startup integration for recovery history."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_recovery_history_service import (
    record_document_recovery_run,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
    run_document_recovery_startup,
)


LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _as_utc(
    value: datetime,
) -> datetime:
    if not isinstance(
        value,
        datetime,
    ):
        raise TypeError(
            "Recovery history clock must "
            "return a datetime."
        )

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def run_document_recovery_startup_with_history(
    *,
    rag: Any,
    settings: DocumentRecoverySettings | None = None,
    now: datetime | None = None,
    recovery_runner: Callable = (
        run_document_recovery_startup
    ),
    history_recorder: Callable = (
        record_document_recovery_run
    ),
    utc_now_fn: Callable[[], datetime] = _utc_now,
    monotonic_fn: Callable[[], float] = perf_counter,
    logger: logging.Logger | None = None,
) -> DocumentRecoveryStartupReport:
    """Run startup recovery and persist a sanitized history row."""
    resolved_logger = (
        LOGGER
        if logger is None
        else logger
    )

    started_at = _as_utc(
        utc_now_fn()
    )

    started_tick = float(
        monotonic_fn()
    )

    report = recovery_runner(
        rag=rag,
        settings=settings,
        now=now,
    )

    finished_at = _as_utc(
        utc_now_fn()
    )

    finished_tick = float(
        monotonic_fn()
    )

    if finished_at < started_at:
        finished_at = started_at

    elapsed_seconds = max(
        0.0,
        finished_tick - started_tick,
    )

    duration_ms = max(
        0,
        int(
            round(
                elapsed_seconds * 1000
            )
        ),
    )

    try:
        history_recorder(
            report,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
    except Exception:
        resolved_logger.warning(
            "Document recovery history "
            "persistence failed."
        )

    return report
