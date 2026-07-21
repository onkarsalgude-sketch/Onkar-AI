"""Sanitized, dependency-injected system health aggregation."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic as default_monotonic
from typing import Literal


ComponentStatus = Literal[
    "healthy",
    "degraded",
    "unavailable",
    "disabled",
]

SystemStatus = Literal[
    "healthy",
    "degraded",
    "unhealthy",
    "initializing",
]


MAX_HEALTH_COMPONENTS = 16

_COMPONENT_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,63}$"
)

_DETAIL_CODE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,63}$"
)

_ALLOWED_COMPONENT_STATUSES = {
    "healthy",
    "degraded",
    "unavailable",
    "disabled",
}


class SystemHealthConfigurationError(
    ValueError
):
    """Raised when health-check definitions are invalid."""


@dataclass(
    frozen=True,
    slots=True,
)
class HealthCheckOutcome:
    """Sanitized result returned by a component health probe."""

    status: ComponentStatus
    detail: str | None = None

    def __post_init__(
        self,
    ) -> None:
        normalized_status = str(
            self.status
        ).strip().casefold()

        if (
            normalized_status
            not in _ALLOWED_COMPONENT_STATUSES
        ):
            raise SystemHealthConfigurationError(
                "Component health status is invalid."
            )

        object.__setattr__(
            self,
            "status",
            normalized_status,
        )

        if self.detail is None:
            return

        normalized_detail = str(
            self.detail
        ).strip().casefold()

        if not _DETAIL_CODE_PATTERN.fullmatch(
            normalized_detail
        ):
            raise SystemHealthConfigurationError(
                "Component health detail code is invalid."
            )

        object.__setattr__(
            self,
            "detail",
            normalized_detail,
        )

    @property
    def healthy(
        self,
    ) -> bool:
        return self.status in {
            "healthy",
            "disabled",
        }


@dataclass(
    frozen=True,
    slots=True,
)
class HealthCheckDefinition:
    """A named dependency probe and its readiness importance."""

    name: str
    check: Callable[
        [],
        HealthCheckOutcome,
    ]
    critical: bool = True

    def __post_init__(
        self,
    ) -> None:
        normalized_name = str(
            self.name
        ).strip().casefold()

        if not _COMPONENT_NAME_PATTERN.fullmatch(
            normalized_name
        ):
            raise SystemHealthConfigurationError(
                "Health component name is invalid."
            )

        if not callable(
            self.check
        ):
            raise SystemHealthConfigurationError(
                "Health component check must be callable."
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )

        object.__setattr__(
            self,
            "critical",
            bool(
                self.critical
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ComponentHealth:
    """Sanitized public health state for one component."""

    name: str
    status: ComponentStatus
    healthy: bool
    critical: bool
    detail: str | None
    checked_at: str
    latency_ms: int


@dataclass(
    frozen=True,
    slots=True,
)
class SystemHealthReport:
    """Aggregated readiness and health result."""

    service: str
    status: SystemStatus
    ready: bool
    healthy: bool
    attention_required: bool
    checked_at: str
    duration_ms: int
    component_count: int
    components: tuple[
        ComponentHealth,
        ...,
    ]


def healthy_outcome(
    detail: str | None = None,
) -> HealthCheckOutcome:
    return HealthCheckOutcome(
        status="healthy",
        detail=detail,
    )


def degraded_outcome(
    detail: str,
) -> HealthCheckOutcome:
    return HealthCheckOutcome(
        status="degraded",
        detail=detail,
    )


def unavailable_outcome(
    detail: str,
) -> HealthCheckOutcome:
    return HealthCheckOutcome(
        status="unavailable",
        detail=detail,
    )


def disabled_outcome(
    detail: str = "disabled",
) -> HealthCheckOutcome:
    return HealthCheckOutcome(
        status="disabled",
        detail=detail,
    )


def _utc_timestamp(
    value: datetime,
) -> str:
    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    normalized = value.astimezone(
        timezone.utc
    )

    return normalized.isoformat(
        timespec="milliseconds"
    ).replace(
        "+00:00",
        "Z",
    )


def _elapsed_milliseconds(
    started: float,
    finished: float,
) -> int:
    elapsed = max(
        0.0,
        float(finished)
        - float(started),
    )

    return int(
        round(
            elapsed * 1000
        )
    )


def _validate_definitions(
    definitions: tuple[
        HealthCheckDefinition,
        ...,
    ],
) -> None:
    if len(definitions) > MAX_HEALTH_COMPONENTS:
        raise SystemHealthConfigurationError(
            "Too many system health components."
        )

    names = [
        definition.name
        for definition in definitions
    ]

    if len(names) != len(
        set(names)
    ):
        raise SystemHealthConfigurationError(
            "System health component names must be unique."
        )


def run_system_health_checks(
    definitions: Iterable[
        HealthCheckDefinition
    ],
    *,
    now: Callable[
        [],
        datetime,
    ] | None = None,
    monotonic: Callable[
        [],
        float,
    ] | None = None,
) -> SystemHealthReport:
    """Run dependency probes without exposing raw failure details."""

    resolved_definitions = tuple(
        definitions
    )

    _validate_definitions(
        resolved_definitions
    )

    now_fn = (
        now
        if now is not None
        else lambda: datetime.now(
            timezone.utc
        )
    )

    monotonic_fn = (
        monotonic
        if monotonic is not None
        else default_monotonic
    )

    started_at = now_fn()
    started_clock = monotonic_fn()

    components: list[
        ComponentHealth
    ] = []

    for definition in resolved_definitions:
        component_checked_at = now_fn()
        component_started = monotonic_fn()

        try:
            outcome = definition.check()

            if not isinstance(
                outcome,
                HealthCheckOutcome,
            ):
                raise TypeError(
                    "Health probe returned an invalid result."
                )
        except Exception:
            outcome = unavailable_outcome(
                "check_failed"
            )

        component_finished = monotonic_fn()

        components.append(
            ComponentHealth(
                name=definition.name,
                status=outcome.status,
                healthy=outcome.healthy,
                critical=definition.critical,
                detail=outcome.detail,
                checked_at=_utc_timestamp(
                    component_checked_at
                ),
                latency_ms=_elapsed_milliseconds(
                    component_started,
                    component_finished,
                ),
            )
        )

    finished_clock = monotonic_fn()

    critical_unavailable = any(
        component.critical
        and component.status == "unavailable"
        for component in components
    )

    degraded_component = any(
        component.status in {
            "degraded",
            "unavailable",
        }
        for component in components
    )

    if not components:
        status: SystemStatus = (
            "initializing"
        )
        ready = False
        healthy = False
        attention_required = False
    elif critical_unavailable:
        status = "unhealthy"
        ready = False
        healthy = False
        attention_required = True
    elif degraded_component:
        status = "degraded"
        ready = True
        healthy = False
        attention_required = True
    else:
        status = "healthy"
        ready = True
        healthy = True
        attention_required = False

    return SystemHealthReport(
        service="system_health",
        status=status,
        ready=ready,
        healthy=healthy,
        attention_required=attention_required,
        checked_at=_utc_timestamp(
            started_at
        ),
        duration_ms=_elapsed_milliseconds(
            started_clock,
            finished_clock,
        ),
        component_count=len(
            components
        ),
        components=tuple(
            components
        ),
    )


def system_health_payload(
    report: SystemHealthReport,
) -> dict:
    """Convert a report to a stable, JSON-compatible payload."""

    return {
        "service": report.service,
        "status": report.status,
        "ready": report.ready,
        "healthy": report.healthy,
        "attention_required": (
            report.attention_required
        ),
        "checked_at": report.checked_at,
        "duration_ms": report.duration_ms,
        "component_count": (
            report.component_count
        ),
        "components": [
            {
                "name": component.name,
                "status": component.status,
                "healthy": component.healthy,
                "critical": component.critical,
                "detail": component.detail,
                "checked_at": (
                    component.checked_at
                ),
                "latency_ms": (
                    component.latency_ms
                ),
            }
            for component in report.components
        ],
    }
