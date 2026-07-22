"""Sanitized system-incident aggregation and reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.services.system_health_service import (
    SystemHealthReport,
)


MAX_INCIDENT_SIGNALS = 16

INCIDENT_SEVERITY_WARNING = "warning"
INCIDENT_SEVERITY_CRITICAL = "critical"

INCIDENT_SOURCE_DEGRADED = "degraded"
INCIDENT_SOURCE_UNAVAILABLE = "unavailable"

_INCIDENT_SEVERITIES = {
    INCIDENT_SEVERITY_WARNING,
    INCIDENT_SEVERITY_CRITICAL,
}

_INCIDENT_SOURCE_STATUSES = {
    INCIDENT_SOURCE_DEGRADED,
    INCIDENT_SOURCE_UNAVAILABLE,
}

_NON_INCIDENT_SOURCE_STATUSES = {
    "healthy",
    "disabled",
}

_COMPONENT_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,63}$"
)

_INCIDENT_KEY_PATTERN = re.compile(
    r"^system_health:[a-z][a-z0-9_]{0,63}$"
)

_DETAIL_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,95}$"
)

_FINGERPRINT_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class SystemIncidentConfigurationError(
    ValueError
):
    """Raised when incident input is unsafe or inconsistent."""


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value
    ).strip().casefold()


def _normalize_component(
    value: Any,
) -> str:
    normalized = _normalize_text(
        value
    )

    if not _COMPONENT_PATTERN.fullmatch(
        normalized
    ):
        raise SystemIncidentConfigurationError(
            "Incident component name is invalid."
        )

    return normalized


def _normalize_incident_key(
    value: Any,
) -> str:
    normalized = _normalize_text(
        value
    )

    if not _INCIDENT_KEY_PATTERN.fullmatch(
        normalized
    ):
        raise SystemIncidentConfigurationError(
            "Incident key is invalid."
        )

    return normalized


def _sanitize_detail(
    value: Any,
) -> str:
    normalized = _normalize_text(
        value
    )

    if not _DETAIL_PATTERN.fullmatch(
        normalized
    ):
        return "check_failed"

    return normalized


def _build_fingerprint(
    *,
    incident_key: str,
    severity: str,
    source_status: str,
    detail: str,
    critical: bool,
) -> str:
    payload = json.dumps(
        {
            "critical": bool(
                critical
            ),
            "detail": detail,
            "incident_key": incident_key,
            "severity": severity,
            "source_status": source_status,
        },
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )

    return hashlib.sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(
    frozen=True,
    slots=True,
)
class IncidentSignal:
    """A sanitized active incident derived from one health component."""

    incident_key: str
    component: str
    severity: str
    source_status: str
    detail: str
    critical: bool
    fingerprint: str = field(
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        component = _normalize_component(
            self.component
        )

        incident_key = _normalize_incident_key(
            self.incident_key
        )

        expected_key = (
            "system_health:"
            + component
        )

        if incident_key != expected_key:
            raise SystemIncidentConfigurationError(
                "Incident key does not match component."
            )

        severity = _normalize_text(
            self.severity
        )

        if severity not in _INCIDENT_SEVERITIES:
            raise SystemIncidentConfigurationError(
                "Incident severity is invalid."
            )

        source_status = _normalize_text(
            self.source_status
        )

        if source_status not in _INCIDENT_SOURCE_STATUSES:
            raise SystemIncidentConfigurationError(
                "Incident source status is invalid."
            )

        detail = _sanitize_detail(
            self.detail
        )

        critical = bool(
            self.critical
        )

        if (
            severity == INCIDENT_SEVERITY_CRITICAL
            and not critical
        ):
            raise SystemIncidentConfigurationError(
                "Critical severity requires a critical component."
            )

        fingerprint = _build_fingerprint(
            incident_key=incident_key,
            severity=severity,
            source_status=source_status,
            detail=detail,
            critical=critical,
        )

        object.__setattr__(
            self,
            "incident_key",
            incident_key,
        )

        object.__setattr__(
            self,
            "component",
            component,
        )

        object.__setattr__(
            self,
            "severity",
            severity,
        )

        object.__setattr__(
            self,
            "source_status",
            source_status,
        )

        object.__setattr__(
            self,
            "detail",
            detail,
        )

        object.__setattr__(
            self,
            "critical",
            critical,
        )

        object.__setattr__(
            self,
            "fingerprint",
            fingerprint,
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "incident_key": self.incident_key,
            "component": self.component,
            "severity": self.severity,
            "source_status": self.source_status,
            "detail": self.detail,
            "critical": self.critical,
            "fingerprint": self.fingerprint,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class IncidentReconciliation:
    """Deterministic transition set between two health evaluations."""

    active: tuple[
        IncidentSignal,
        ...,
    ]

    opened: tuple[
        IncidentSignal,
        ...,
    ]

    updated: tuple[
        IncidentSignal,
        ...,
    ]

    resolved: tuple[
        IncidentSignal,
        ...,
    ]

    unchanged: tuple[
        IncidentSignal,
        ...,
    ]

    def __post_init__(
        self,
    ) -> None:
        groups = (
            self.active,
            self.opened,
            self.updated,
            self.resolved,
            self.unchanged,
        )

        for group in groups:
            if not isinstance(
                group,
                tuple,
            ):
                raise SystemIncidentConfigurationError(
                    "Incident reconciliation groups must be tuples."
                )

            if len(group) > MAX_INCIDENT_SIGNALS:
                raise SystemIncidentConfigurationError(
                    "Incident reconciliation exceeds the signal limit."
                )

            for signal in group:
                if not isinstance(
                    signal,
                    IncidentSignal,
                ):
                    raise SystemIncidentConfigurationError(
                        "Incident reconciliation contains an invalid signal."
                    )

        active_keys = {
            signal.incident_key
            for signal in self.active
        }

        transition_groups = (
            self.opened,
            self.updated,
            self.unchanged,
        )

        for group in transition_groups:
            for signal in group:
                if signal.incident_key not in active_keys:
                    raise SystemIncidentConfigurationError(
                        "Active incident transition is inconsistent."
                    )

        transition_keys = [
            {
                signal.incident_key
                for signal in group
            }
            for group in (
                self.opened,
                self.updated,
                self.resolved,
                self.unchanged,
            )
        ]

        for index, keys in enumerate(
            transition_keys
        ):
            for other_keys in transition_keys[
                index + 1:
            ]:
                if keys & other_keys:
                    raise SystemIncidentConfigurationError(
                        "Incident transition groups overlap."
                    )

    @property
    def active_count(
        self,
    ) -> int:
        return len(
            self.active
        )

    @property
    def warning_count(
        self,
    ) -> int:
        return sum(
            signal.severity
            == INCIDENT_SEVERITY_WARNING
            for signal in self.active
        )

    @property
    def critical_count(
        self,
    ) -> int:
        return sum(
            signal.severity
            == INCIDENT_SEVERITY_CRITICAL
            for signal in self.active
        )

    @property
    def has_critical(
        self,
    ) -> bool:
        return self.critical_count > 0


def build_incident_signals(
    report: SystemHealthReport,
) -> tuple[
    IncidentSignal,
    ...,
]:
    """Convert degraded and unavailable health components into signals."""

    if not isinstance(
        report,
        SystemHealthReport,
    ):
        raise SystemIncidentConfigurationError(
            "A valid system-health report is required."
        )

    components = tuple(
        report.components
    )

    if len(components) > MAX_INCIDENT_SIGNALS:
        raise SystemIncidentConfigurationError(
            "System-health report exceeds the incident signal limit."
        )

    signals: list[
        IncidentSignal
    ] = []

    for component in components:
        name = _normalize_component(
            component.name
        )

        source_status = _normalize_text(
            component.status
        )

        if source_status in _NON_INCIDENT_SOURCE_STATUSES:
            continue

        if source_status not in _INCIDENT_SOURCE_STATUSES:
            raise SystemIncidentConfigurationError(
                "Health component status cannot be converted to an incident."
            )

        critical = bool(
            component.critical
        )

        severity = (
            INCIDENT_SEVERITY_CRITICAL
            if (
                source_status
                == INCIDENT_SOURCE_UNAVAILABLE
                and critical
            )
            else INCIDENT_SEVERITY_WARNING
        )

        signals.append(
            IncidentSignal(
                incident_key=(
                    "system_health:"
                    + name
                ),
                component=name,
                severity=severity,
                source_status=source_status,
                detail=_sanitize_detail(
                    component.detail
                ),
                critical=critical,
            )
        )

    return tuple(
        signals
    )


def _normalize_previous_signals(
    previous_open_signals: Iterable[
        IncidentSignal
    ],
) -> tuple[
    IncidentSignal,
    ...,
]:
    try:
        signals = tuple(
            previous_open_signals
        )
    except TypeError as exc:
        raise SystemIncidentConfigurationError(
            "Previous incident signals must be iterable."
        ) from exc

    if len(signals) > MAX_INCIDENT_SIGNALS:
        raise SystemIncidentConfigurationError(
            "Previous incident signals exceed the limit."
        )

    seen_keys: set[str] = set()

    for signal in signals:
        if not isinstance(
            signal,
            IncidentSignal,
        ):
            raise SystemIncidentConfigurationError(
                "Previous incident signal is invalid."
            )

        if signal.incident_key in seen_keys:
            raise SystemIncidentConfigurationError(
                "Previous incident signals contain duplicate keys."
            )

        seen_keys.add(
            signal.incident_key
        )

    return signals


def reconcile_incident_signals(
    previous_open_signals: Iterable[
        IncidentSignal
    ],
    report: SystemHealthReport,
) -> IncidentReconciliation:
    """Classify opened, updated, resolved and unchanged incidents."""

    previous = _normalize_previous_signals(
        previous_open_signals
    )

    active = build_incident_signals(
        report
    )

    previous_by_key = {
        signal.incident_key: signal
        for signal in previous
    }

    active_by_key = {
        signal.incident_key: signal
        for signal in active
    }

    opened = tuple(
        signal
        for signal in active
        if signal.incident_key
        not in previous_by_key
    )

    updated = tuple(
        signal
        for signal in active
        if (
            signal.incident_key
            in previous_by_key
            and signal.fingerprint
            != previous_by_key[
                signal.incident_key
            ].fingerprint
        )
    )

    unchanged = tuple(
        signal
        for signal in active
        if (
            signal.incident_key
            in previous_by_key
            and signal.fingerprint
            == previous_by_key[
                signal.incident_key
            ].fingerprint
        )
    )

    resolved = tuple(
        signal
        for signal in previous
        if signal.incident_key
        not in active_by_key
    )

    return IncidentReconciliation(
        active=active,
        opened=opened,
        updated=updated,
        resolved=resolved,
        unchanged=unchanged,
    )


def incident_reconciliation_payload(
    reconciliation: IncidentReconciliation,
) -> dict[str, Any]:
    """Return a sanitized persistence/API-ready incident payload."""

    if not isinstance(
        reconciliation,
        IncidentReconciliation,
    ):
        raise SystemIncidentConfigurationError(
            "A valid incident reconciliation is required."
        )

    return {
        "service": "system_incidents",
        "active_count": reconciliation.active_count,
        "warning_count": reconciliation.warning_count,
        "critical_count": reconciliation.critical_count,
        "has_critical": reconciliation.has_critical,
        "opened_count": len(
            reconciliation.opened
        ),
        "updated_count": len(
            reconciliation.updated
        ),
        "resolved_count": len(
            reconciliation.resolved
        ),
        "unchanged_count": len(
            reconciliation.unchanged
        ),
        "active": [
            signal.to_dict()
            for signal in reconciliation.active
        ],
        "opened": [
            signal.to_dict()
            for signal in reconciliation.opened
        ],
        "updated": [
            signal.to_dict()
            for signal in reconciliation.updated
        ],
        "resolved": [
            signal.to_dict()
            for signal in reconciliation.resolved
        ],
        "unchanged": [
            signal.to_dict()
            for signal in reconciliation.unchanged
        ],
    }
