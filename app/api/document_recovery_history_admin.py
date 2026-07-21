"""Authenticated recovery-history and operational-metrics APIs."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)

from app.api.document_recovery_admin import (
    validate_document_recovery_monitoring_settings,
    verify_branch_merge_bearer,
)
from app.services.document_recovery_history_service import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    list_document_recovery_runs,
    summarize_document_recovery_runs,
)


_HISTORY_PATH = (
    "/admin/document-recovery/history"
)

_METRICS_PATH = (
    "/admin/document-recovery/metrics"
)

_ALLOWED_STATUSES = (
    "completed",
    "completed_with_failures",
    "disabled",
    "failed",
    "skipped_lock_held",
)

_SAFE_RUN_FIELDS = (
    "run_id",
    "status",
    "recovery_enabled",
    "started_at",
    "finished_at",
    "duration_ms",
    "total_examined",
    "candidate_count",
    "processing_recovered_count",
    "deleting_completed_count",
    "failure_count",
    "skipped_count",
    "recent_count",
    "invalid_timestamp_count",
    "deferred_count",
)

_COUNT_FIELDS = (
    "duration_ms",
    "total_examined",
    "candidate_count",
    "processing_recovered_count",
    "deleting_completed_count",
    "failure_count",
    "skipped_count",
    "recent_count",
    "invalid_timestamp_count",
    "deferred_count",
)


def _safe_nonnegative_integer(
    value: Any,
) -> int:
    if isinstance(value, bool):
        return 0

    try:
        normalized = int(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return 0

    return max(
        0,
        normalized,
    )


def _safe_nonnegative_float(
    value: Any,
) -> float:
    if isinstance(value, bool):
        return 0.0

    try:
        normalized = float(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return 0.0

    return max(
        0.0,
        normalized,
    )


def _safe_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value)


def _sanitize_run(
    value: Any,
) -> dict:
    source = (
        value
        if isinstance(value, dict)
        else {}
    )

    sanitized = {
        field_name: source.get(
            field_name
        )
        for field_name in _SAFE_RUN_FIELDS
    }

    sanitized["run_id"] = _safe_text(
        sanitized["run_id"]
    )

    status = _safe_text(
        sanitized["status"]
    ).strip().casefold()

    sanitized["status"] = (
        status
        if status in _ALLOWED_STATUSES
        else "unknown"
    )

    sanitized["recovery_enabled"] = bool(
        sanitized[
            "recovery_enabled"
        ]
    )

    sanitized["started_at"] = _safe_text(
        sanitized["started_at"]
    )

    sanitized["finished_at"] = _safe_text(
        sanitized["finished_at"]
    )

    for field_name in _COUNT_FIELDS:
        sanitized[field_name] = (
            _safe_nonnegative_integer(
                sanitized[field_name]
            )
        )

    return sanitized


def _sanitize_metrics(
    value: Any,
) -> dict:
    source = (
        value
        if isinstance(value, dict)
        else {}
    )

    raw_status_counts = source.get(
        "status_counts"
    )

    if not isinstance(
        raw_status_counts,
        dict,
    ):
        raw_status_counts = {}

    status_counts = {
        status: _safe_nonnegative_integer(
            raw_status_counts.get(
                status,
                0,
            )
        )
        for status in _ALLOWED_STATUSES
    }

    latest_run = source.get(
        "latest_run"
    )

    return {
        "total_runs": (
            _safe_nonnegative_integer(
                source.get(
                    "total_runs",
                    0,
                )
            )
        ),
        "status_counts": status_counts,
        "failure_runs": (
            _safe_nonnegative_integer(
                source.get(
                    "failure_runs",
                    0,
                )
            )
        ),
        "total_failures": (
            _safe_nonnegative_integer(
                source.get(
                    "total_failures",
                    0,
                )
            )
        ),
        "average_duration_ms": (
            _safe_nonnegative_float(
                source.get(
                    "average_duration_ms",
                    0.0,
                )
            )
        ),
        "latest_run": (
            _sanitize_run(
                latest_run
            )
            if isinstance(
                latest_run,
                dict,
            )
            else None
        ),
    }


def _authenticate(
    request: Request,
    settings: Any,
) -> None:
    authenticated = (
        verify_branch_merge_bearer(
            request.headers.get(
                "authorization"
            ),
            settings.token_sha256,
        )
    )

    if authenticated:
        return

    raise HTTPException(
        status_code=401,
        detail=(
            "Valid recovery monitoring "
            "authorization is required."
        ),
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def _history_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Document recovery history "
            "is unavailable."
        ),
    )


def create_document_recovery_history_admin_router(
    settings: Any,
    *,
    history_lister: Callable = (
        list_document_recovery_runs
    ),
    metrics_summarizer: Callable = (
        summarize_document_recovery_runs
    ),
) -> APIRouter:
    """Create secure read-only recovery history routes."""
    validate_document_recovery_monitoring_settings(
        settings
    )

    router = APIRouter()

    @router.get(
        _HISTORY_PATH,
        operation_id=(
            "get_document_recovery_history"
        ),
        tags=["admin"],
    )
    async def get_document_recovery_history(
        request: Request,
        limit: int = Query(
            DEFAULT_HISTORY_LIMIT,
            ge=1,
            le=MAX_HISTORY_LIMIT,
        ),
    ) -> dict:
        _authenticate(
            request,
            settings,
        )

        try:
            raw_history = history_lister(
                limit
            )
        except Exception:
            raise _history_unavailable()

        if not isinstance(
            raw_history,
            list,
        ):
            raise _history_unavailable()

        history = [
            _sanitize_run(row)
            for row in raw_history
            if isinstance(
                row,
                dict,
            )
        ]

        return {
            "service": "document_recovery",
            "limit": int(limit),
            "count": len(history),
            "history": history,
        }

    @router.get(
        _METRICS_PATH,
        operation_id=(
            "get_document_recovery_metrics"
        ),
        tags=["admin"],
    )
    async def get_document_recovery_metrics(
        request: Request,
        limit: int = Query(
            MAX_HISTORY_LIMIT,
            ge=1,
            le=MAX_HISTORY_LIMIT,
        ),
    ) -> dict:
        _authenticate(
            request,
            settings,
        )

        try:
            raw_metrics = (
                metrics_summarizer(
                    limit
                )
            )
        except Exception:
            raise _history_unavailable()

        if not isinstance(
            raw_metrics,
            dict,
        ):
            raise _history_unavailable()

        return {
            "service": "document_recovery",
            "window_limit": int(limit),
            "metrics": _sanitize_metrics(
                raw_metrics
            ),
        }

    return router
