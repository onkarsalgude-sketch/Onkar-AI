"""Sanitized, default-disabled HTTPS webhook delivery for incidents."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from app.config.system_incident_alerting import (
    SystemIncidentAlertingSettings,
    validate_system_incident_alerting_settings,
)


MAX_ALERT_TRANSITIONS = 16
MAX_ALERT_PAYLOAD_BYTES = 32_768

_ALLOWED_TRANSITIONS = (
    "opened",
    "updated",
    "resolved",
)

_ALLOWED_SEVERITIES = {
    "warning",
    "critical",
}

_ALLOWED_SOURCE_STATUSES = {
    "degraded",
    "unavailable",
}

_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9._:-]+$"
)

_COMPONENT_PATTERN = re.compile(
    r"^[a-z0-9_]+$"
)

_DETAIL_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_.:-]*$"
)

_FINGERPRINT_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class SystemIncidentAlertError(
    RuntimeError
):
    """Raised when an incident alert cannot be built or delivered safely."""


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
        or len(
            normalized
        ) > maximum
        or not _IDENTIFIER_PATTERN.fullmatch(
            normalized
        )
    ):
        return fallback

    return normalized


def _safe_component(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if (
        not normalized
        or len(
            normalized
        ) > 64
        or not _COMPONENT_PATTERN.fullmatch(
            normalized
        )
    ):
        return "unknown"

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


def _safe_detail(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if (
        not normalized
        or len(
            normalized
        ) > 96
        or not _DETAIL_PATTERN.fullmatch(
            normalized
        )
    ):
        return "check_failed"

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


def _safe_fingerprint(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if not _FINGERPRINT_PATTERN.fullmatch(
        normalized
    ):
        return "0" * 64

    return normalized


def _utc_timestamp(
    value: Any,
    *,
    fallback: str | None = None,
) -> str:
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

        if candidate.endswith(
            "Z"
        ):
            candidate = (
                candidate[:-1]
                + "+00:00"
            )

        try:
            normalized = datetime.fromisoformat(
                candidate
            )
        except ValueError:
            if fallback is not None:
                return fallback

            raise SystemIncidentAlertError(
                "System incident alert timestamp is invalid."
            )
    else:
        if fallback is not None:
            return fallback

        raise SystemIncidentAlertError(
            "System incident alert timestamp is invalid."
        )

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


def _sanitize_transition(
    transition: str,
    raw_signal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "transition": transition,
        "state": (
            "resolved"
            if transition == "resolved"
            else "open"
        ),
        "incident_key": _safe_identifier(
            raw_signal.get(
                "incident_key"
            ),
            maximum=128,
            fallback=(
                "system_health:unknown"
            ),
        ),
        "component": _safe_component(
            raw_signal.get(
                "component"
            )
        ),
        "severity": _safe_choice(
            raw_signal.get(
                "severity"
            ),
            allowed=_ALLOWED_SEVERITIES,
            fallback="warning",
        ),
        "source_status": _safe_choice(
            raw_signal.get(
                "source_status"
            ),
            allowed=(
                _ALLOWED_SOURCE_STATUSES
            ),
            fallback="unavailable",
        ),
        "detail": _safe_detail(
            raw_signal.get(
                "detail"
            )
        ),
        "critical": _safe_boolean(
            raw_signal.get(
                "critical"
            )
        ),
        "fingerprint": _safe_fingerprint(
            raw_signal.get(
                "fingerprint"
            )
        ),
    }


def build_system_incident_alert_payload(
    evaluation: dict[str, Any],
    *,
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> dict[str, Any] | None:
    """Build one bounded alert payload, suppressing unchanged transitions."""
    if not isinstance(
        evaluation,
        dict,
    ):
        raise SystemIncidentAlertError(
            "System incident alert evaluation is invalid."
        )

    now_fn = (
        now
        if now is not None
        else lambda: datetime.now(
            timezone.utc
        )
    )

    if not callable(
        now_fn
    ):
        raise SystemIncidentAlertError(
            "System incident alert clock is invalid."
        )

    sent_at = _utc_timestamp(
        now_fn()
    )

    observed_at = _utc_timestamp(
        evaluation.get(
            "observed_at"
        ),
        fallback=sent_at,
    )

    transitions: list[
        dict[str, Any]
    ] = []

    for transition in _ALLOWED_TRANSITIONS:
        raw_group = evaluation.get(
            transition,
            [],
        )

        if not isinstance(
            raw_group,
            list,
        ):
            raise SystemIncidentAlertError(
                "System incident alert evaluation is invalid."
            )

        for raw_signal in raw_group:
            if not isinstance(
                raw_signal,
                dict,
            ):
                continue

            transitions.append(
                _sanitize_transition(
                    transition,
                    raw_signal,
                )
            )

            if len(
                transitions
            ) > MAX_ALERT_TRANSITIONS:
                raise SystemIncidentAlertError(
                    "System incident alert transition limit exceeded."
                )

    if not transitions:
        return None

    payload = {
        "service": "system_incidents",
        "event": "incident_transitions",
        "observed_at": observed_at,
        "sent_at": sent_at,
        "transition_count": len(
            transitions
        ),
        "transitions": transitions,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(
            ",",
            ":",
        ),
        sort_keys=True,
    ).encode(
        "utf-8"
    )

    if len(
        serialized
    ) > MAX_ALERT_PAYLOAD_BYTES:
        raise SystemIncidentAlertError(
            "System incident alert payload exceeds the size limit."
        )

    return payload


def _send_https_json(
    webhook_url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> None:
    response = None

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout_seconds,
            allow_redirects=False,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": (
                    "Onkar-AI-System-Incidents/1"
                ),
            },
        )

        if not (
            200
            <= int(
                response.status_code
            )
            < 300
        ):
            raise RuntimeError(
                "Webhook returned a non-success status."
            )
    finally:
        if response is not None:
            response.close()


def deliver_system_incident_alerts(
    settings: SystemIncidentAlertingSettings,
    evaluation: dict[str, Any],
    *,
    sender: Callable[
        [
            str,
            dict[str, Any],
            float,
        ],
        None,
    ] = _send_https_json,
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> dict[str, Any]:
    """Deliver one sanitized transition payload to an HTTPS webhook."""
    validate_system_incident_alerting_settings(
        settings
    )

    if not settings.enabled:
        return {
            "service": "system_incident_alerts",
            "enabled": False,
            "attempted": False,
            "delivered": False,
            "transition_count": 0,
        }

    if not callable(
        sender
    ):
        raise SystemIncidentAlertError(
            "System incident alert sender is invalid."
        )

    payload = build_system_incident_alert_payload(
        evaluation,
        now=now,
    )

    if payload is None:
        return {
            "service": "system_incident_alerts",
            "enabled": True,
            "attempted": False,
            "delivered": False,
            "transition_count": 0,
        }

    try:
        sender(
            settings.webhook_url,
            payload,
            settings.timeout_seconds,
        )
    except SystemIncidentAlertError:
        raise
    except Exception as error:
        raise SystemIncidentAlertError(
            "System incident alert delivery failed."
        ) from error

    return {
        "service": "system_incident_alerts",
        "enabled": True,
        "attempted": True,
        "delivered": True,
        "transition_count": int(
            payload["transition_count"]
        ),
    }
