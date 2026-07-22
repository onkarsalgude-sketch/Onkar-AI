"""Secure read-only administration routes for system incidents."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)

from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
    validate_system_health_monitoring_settings,
)
from app.services.branch_merge_security import verify_branch_merge_bearer
from app.services.system_incident_history_service import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    list_system_incidents,
    summarize_system_incidents,
)


SYSTEM_INCIDENT_HISTORY_PATH = (
    "/admin/system-incidents/history"
)

SYSTEM_INCIDENT_SUMMARY_PATH = (
    "/admin/system-incidents/summary"
)

_SAFE_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]+$"
)

_SAFE_DETAIL_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_.:-]*$"
)

_SAFE_FINGERPRINT_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)

_ALLOWED_SEVERITIES = {
    "warning",
    "critical",
}

_ALLOWED_SOURCE_STATUSES = {
    "degraded",
    "unavailable",
}

_ALLOWED_STATES = {
    "open",
    "resolved",
}

_MAX_SAFE_COUNT = 1_000_000_000


def _authenticate(
    request: Request,
    settings: SystemHealthMonitoringSettings,
) -> None:
    authenticated = verify_branch_merge_bearer(
        request.headers.get(
            "authorization"
        ),
        settings.token_sha256,
    )

    if authenticated:
        return

    raise HTTPException(
        status_code=401,
        detail=(
            "Valid incident monitoring "
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
            "System incident history "
            "is unavailable."
        ),
    )


def _safe_identifier(
    value: Any,
    *,
    maximum: int,
    fallback: str,
) -> str:
    normalized = str(
        value
    ).strip()

    if (
        not normalized
        or len(normalized) > maximum
        or not _SAFE_IDENTIFIER_PATTERN.fullmatch(
            normalized
        )
    ):
        return fallback

    return normalized


def _safe_detail(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if (
        not normalized
        or len(normalized) > 96
        or not _SAFE_DETAIL_PATTERN.fullmatch(
            normalized
        )
    ):
        return "check_failed"

    return normalized


def _safe_choice(
    value: Any,
    *,
    allowed: set[str],
    fallback: str,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if normalized not in allowed:
        return fallback

    return normalized


def _safe_boolean(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    if value in (
        0,
        1,
    ):
        return bool(
            value
        )

    return False


def _safe_count(
    value: Any,
    *,
    minimum: int = 0,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        return minimum

    try:
        normalized = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return minimum

    return max(
        minimum,
        min(
            normalized,
            _MAX_SAFE_COUNT,
        ),
    )


def _safe_timestamp(
    value: Any,
) -> str | None:
    if isinstance(
        value,
        datetime,
    ):
        normalized = value
    elif isinstance(
        value,
        str,
    ):
        candidate = value.strip()

        if len(candidate) > 64:
            return None

        if candidate.endswith("Z"):
            candidate = (
                candidate[:-1]
                + "+00:00"
            )

        try:
            normalized = datetime.fromisoformat(
                candidate
            )
        except ValueError:
            return None
    else:
        return None

    if (
        normalized.tzinfo is None
        or normalized.utcoffset() is None
    ):
        normalized = normalized.replace(
            tzinfo=timezone.utc
        )

    return (
        normalized
        .astimezone(timezone.utc)
        .isoformat()
    )


def _safe_fingerprint(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if not _SAFE_FINGERPRINT_PATTERN.fullmatch(
        normalized
    ):
        return "0" * 64

    return normalized


def _sanitize_incident(
    raw_incident: dict[str, Any],
) -> dict[str, Any]:
    state = _safe_choice(
        raw_incident.get(
            "state"
        ),
        allowed=_ALLOWED_STATES,
        fallback="resolved",
    )

    return {
        "incident_id": _safe_identifier(
            raw_incident.get(
                "incident_id"
            ),
            maximum=128,
            fallback="invalid",
        ),
        "incident_key": _safe_identifier(
            raw_incident.get(
                "incident_key"
            ),
            maximum=128,
            fallback=(
                "system_health:unknown"
            ),
        ),
        "component": _safe_identifier(
            raw_incident.get(
                "component"
            ),
            maximum=64,
            fallback="unknown",
        ).casefold(),
        "severity": _safe_choice(
            raw_incident.get(
                "severity"
            ),
            allowed=_ALLOWED_SEVERITIES,
            fallback="warning",
        ),
        "source_status": _safe_choice(
            raw_incident.get(
                "source_status"
            ),
            allowed=(
                _ALLOWED_SOURCE_STATUSES
            ),
            fallback="unavailable",
        ),
        "detail": _safe_detail(
            raw_incident.get(
                "detail"
            )
        ),
        "critical": _safe_boolean(
            raw_incident.get(
                "critical"
            )
        ),
        "state": state,
        "fingerprint": _safe_fingerprint(
            raw_incident.get(
                "fingerprint"
            )
        ),
        "opened_at": _safe_timestamp(
            raw_incident.get(
                "opened_at"
            )
        ),
        "last_seen_at": _safe_timestamp(
            raw_incident.get(
                "last_seen_at"
            )
        ),
        "resolved_at": (
            _safe_timestamp(
                raw_incident.get(
                    "resolved_at"
                )
            )
            if state == "resolved"
            else None
        ),
        "occurrence_count": _safe_count(
            raw_incident.get(
                "occurrence_count"
            ),
            minimum=1,
        ),
    }


def _sanitize_summary(
    raw_summary: dict[str, Any],
) -> dict[str, Any]:
    latest_incident = raw_summary.get(
        "latest_incident"
    )

    return {
        "total_incidents": _safe_count(
            raw_summary.get(
                "total_incidents"
            )
        ),
        "active_count": _safe_count(
            raw_summary.get(
                "active_count"
            )
        ),
        "resolved_count": _safe_count(
            raw_summary.get(
                "resolved_count"
            )
        ),
        "active_warning_count": _safe_count(
            raw_summary.get(
                "active_warning_count"
            )
        ),
        "active_critical_count": _safe_count(
            raw_summary.get(
                "active_critical_count"
            )
        ),
        "has_active_critical": _safe_boolean(
            raw_summary.get(
                "has_active_critical"
            )
        ),
        "total_occurrences": _safe_count(
            raw_summary.get(
                "total_occurrences"
            )
        ),
        "latest_incident": (
            _sanitize_incident(
                latest_incident
            )
            if isinstance(
                latest_incident,
                dict,
            )
            else None
        ),
    }


def create_system_incident_admin_router(
    settings: SystemHealthMonitoringSettings,
    *,
    history_lister: Callable = (
        list_system_incidents
    ),
    summary_summarizer: Callable = (
        summarize_system_incidents
    ),
) -> APIRouter:
    """Create authenticated, read-only system-incident routes."""
    validate_system_health_monitoring_settings(
        settings
    )

    if not callable(
        history_lister
    ):
        raise TypeError(
            "System incident history lister "
            "must be callable."
        )

    if not callable(
        summary_summarizer
    ):
        raise TypeError(
            "System incident summary provider "
            "must be callable."
        )

    router = APIRouter()

    @router.get(
        SYSTEM_INCIDENT_HISTORY_PATH,
        operation_id=(
            "get_system_incident_history"
        ),
        tags=["admin"],
    )
    async def get_system_incident_history(
        request: Request,
        limit: int = Query(
            DEFAULT_HISTORY_LIMIT,
            ge=1,
            le=MAX_HISTORY_LIMIT,
        ),
        state: str | None = Query(
            None,
            pattern="^(open|resolved)$",
        ),
    ) -> dict[str, Any]:
        _authenticate(
            request,
            settings,
        )

        try:
            raw_history = history_lister(
                limit,
                state=state,
            )
        except Exception:
            raise _history_unavailable()

        if not isinstance(
            raw_history,
            list,
        ):
            raise _history_unavailable()

        history = [
            _sanitize_incident(
                row
            )
            for row in raw_history
            if isinstance(
                row,
                dict,
            )
        ]

        return {
            "service": "system_incidents",
            "limit": int(
                limit
            ),
            "state": state,
            "count": len(
                history
            ),
            "history": history,
        }

    @router.get(
        SYSTEM_INCIDENT_SUMMARY_PATH,
        operation_id=(
            "get_system_incident_summary"
        ),
        tags=["admin"],
    )
    async def get_system_incident_summary(
        request: Request,
        limit: int = Query(
            MAX_HISTORY_LIMIT,
            ge=1,
            le=MAX_HISTORY_LIMIT,
        ),
    ) -> dict[str, Any]:
        _authenticate(
            request,
            settings,
        )

        try:
            raw_summary = (
                summary_summarizer(
                    limit
                )
            )
        except Exception:
            raise _history_unavailable()

        if not isinstance(
            raw_summary,
            dict,
        ):
            raise _history_unavailable()

        return {
            "service": "system_incidents",
            "window_limit": int(
                limit
            ),
            "summary": _sanitize_summary(
                raw_summary
            ),
        }

    return router
