"""Authenticated, read-only system-health monitoring API."""

from __future__ import annotations

import logging

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)

from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
    validate_system_health_monitoring_settings,
)
from app.services.branch_merge_security import (
    verify_branch_merge_bearer,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    SystemHealthReport,
    run_system_health_checks,
    system_health_payload,
    unavailable_outcome,
)


from app.services.system_incident_history_service import (
    record_system_incident_evaluation,
)


logger = logging.getLogger(__name__)


SYSTEM_HEALTH_STATUS_PATH = (
    "/admin/system-health/status"
)


def _fallback_health_report() -> SystemHealthReport:
    """Return a sanitized failure report for monitoring-runtime errors."""

    return run_system_health_checks(
        (
            HealthCheckDefinition(
                name="health_runtime",
                check=lambda: unavailable_outcome(
                    "check_failed"
                ),
                critical=True,
            ),
        )
    )


def _run_health_report(
    request: Request,
    *,
    definitions_provider: Callable[
        [Request],
        Iterable[
            HealthCheckDefinition
        ],
    ],
    health_runner: Callable[
        [
            Iterable[
                HealthCheckDefinition
            ]
        ],
        SystemHealthReport,
    ],
) -> SystemHealthReport:
    try:
        definitions = definitions_provider(
            request
        )

        report = health_runner(
            definitions
        )

        if not isinstance(
            report,
            SystemHealthReport,
        ):
            raise TypeError(
                "System-health runner returned an invalid report."
            )

        return report
    except Exception:
        return _fallback_health_report()


def create_system_health_admin_router(
    settings: SystemHealthMonitoringSettings,
    *,
    definitions_provider: Callable[
        [Request],
        Iterable[
            HealthCheckDefinition
        ],
    ],
    health_runner: Callable[
        [
            Iterable[
                HealthCheckDefinition
            ]
        ],
        SystemHealthReport,
    ] = run_system_health_checks,
    incident_recorder: Callable | None = None,
    incident_db_path: str | None = None,
) -> APIRouter:
    """Build the authenticated system-health status router."""

    validate_system_health_monitoring_settings(
        settings
    )

    if not callable(definitions_provider):
        raise TypeError(
            "System-health definitions provider must be callable."
        )

    if not callable(health_runner):
        raise TypeError(
            "System-health runner must be callable."
        )

    if (
        incident_recorder is not None
        and not callable(incident_recorder)
    ):
        raise TypeError(
            "System incident recorder must be callable."
        )

    router = APIRouter()

    @router.get(
        SYSTEM_HEALTH_STATUS_PATH,
        operation_id="get_system_health_status",
        tags=["admin"],
    )
    def get_system_health_status(
        request: Request,
    ) -> dict[str, Any]:
        authenticated = verify_branch_merge_bearer(
            request.headers.get("authorization"),
            settings.token_sha256,
        )

        if not authenticated:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Valid system-health monitoring "
                    "authorization is required."
                ),
                headers={
                    "WWW-Authenticate": "Bearer",
                },
            )

        report = _run_health_report(
            request,
            definitions_provider=definitions_provider,
            health_runner=health_runner,
        )

        if incident_recorder is not None:
            try:
                incident_recorder(
                    report,
                    observed_at=report.checked_at,
                    db_path=incident_db_path,
                )
            except Exception:
                logger.warning(
                    "System incident persistence failed."
                )

        return system_health_payload(report)

    return router
