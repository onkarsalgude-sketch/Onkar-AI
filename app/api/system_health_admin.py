"""Authenticated, read-only system-health monitoring API."""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks

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


from app.config.system_incident_alerting import (
    SystemIncidentAlertingSettings,
    validate_system_incident_alerting_settings,
)
from app.services.system_incident_alert_service import (
    deliver_system_incident_alerts,
)
from app.services.system_incident_alert_outbox_service import (
    enqueue_system_incident_alert,
)
from app.services.system_incident_alert_outbox_worker import (
    process_next_system_incident_alert,
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


def _has_alert_transitions(
    evaluation: Any,
) -> bool:
    if not isinstance(
        evaluation,
        dict,
    ):
        return False

    for transition_name in (
        "opened",
        "updated",
        "resolved",
    ):
        group = evaluation.get(
            transition_name
        )

        if (
            isinstance(
                group,
                list,
            )
            and any(
                isinstance(
                    item,
                    dict,
                )
                for item in group
            )
        ):
            return True

    return False


def _deliver_incident_alert_safely(
    deliverer: Callable,
    settings: SystemIncidentAlertingSettings,
    evaluation: dict[str, Any],
) -> None:
    try:
        deliverer(
            settings,
            evaluation,
        )
    except Exception:
        logger.warning(
            "System incident alert delivery failed."
        )

def _run_incident_alert_worker_safely(
    worker: Callable,
    settings: SystemIncidentAlertingSettings,
    db_path: str | None,
) -> None:
    try:
        worker(
            settings,
            db_path=db_path,
        )
    except Exception:
        logger.warning(
            "System incident alert worker failed."
        )


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
    incident_alert_settings: (
        SystemIncidentAlertingSettings
        | None
    ) = None,
    incident_alert_deliverer: Callable | None = None,
    incident_alert_enqueuer: Callable | None = None,
    incident_alert_worker: Callable | None = None,
) -> APIRouter:
    """Build the authenticated system-health status router."""
    validate_system_health_monitoring_settings(
        settings
    )

    if not callable(
        definitions_provider
    ):
        raise TypeError(
            "System-health definitions provider "
            "must be callable."
        )

    if not callable(
        health_runner
    ):
        raise TypeError(
            "System-health runner "
            "must be callable."
        )

    if (
        incident_recorder is not None
        and not callable(
            incident_recorder
        )
    ):
        raise TypeError(
            "System incident recorder "
            "must be callable."
        )

    if incident_alert_settings is not None:
        validate_system_incident_alerting_settings(
            incident_alert_settings
        )

    if (
        incident_alert_deliverer is not None
        and not callable(
            incident_alert_deliverer
        )
    ):
        raise TypeError(
            "System incident alert deliverer "
            "must be callable."
        )

    legacy_direct_delivery = (
        incident_alert_deliverer is not None
        and incident_alert_enqueuer is None
        and incident_alert_worker is None
    )

    resolved_incident_alert_enqueuer = None
    resolved_incident_alert_worker = None

    if not legacy_direct_delivery:
        resolved_incident_alert_enqueuer = (
            incident_alert_enqueuer
            if incident_alert_enqueuer is not None
            else enqueue_system_incident_alert
        )

        resolved_incident_alert_worker = (
            incident_alert_worker
            if incident_alert_worker is not None
            else process_next_system_incident_alert
        )

        if not callable(
            resolved_incident_alert_enqueuer
        ):
            raise TypeError(
                "System incident alert enqueuer "
                "must be callable."
            )

        if not callable(
            resolved_incident_alert_worker
        ):
            raise TypeError(
                "System incident alert worker "
                "must be callable."
            )

    router = APIRouter()

    @router.get(
        SYSTEM_HEALTH_STATUS_PATH,
        operation_id="get_system_health_status",
        tags=["admin"],
    )
    def get_system_health_status(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        authenticated = verify_branch_merge_bearer(
            request.headers.get(
                "authorization"
            ),
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
            definitions_provider=(
                definitions_provider
            ),
            health_runner=health_runner,
        )

        evaluation = None

        if incident_recorder is not None:
            try:
                evaluation = incident_recorder(
                    report,
                    observed_at=report.checked_at,
                    db_path=incident_db_path,
                )
            except Exception:
                logger.warning(
                    "System incident persistence failed."
                )

        if (
            incident_alert_settings is not None
            and incident_alert_settings.enabled
            and _has_alert_transitions(
                evaluation
            )
        ):
            if legacy_direct_delivery:
                background_tasks.add_task(
                    _deliver_incident_alert_safely,
                    incident_alert_deliverer,
                    incident_alert_settings,
                    dict(
                        evaluation
                    ),
                )
            else:
                queued = False

                try:
                    enqueue_result = (
                        resolved_incident_alert_enqueuer(
                            incident_alert_settings,
                            dict(
                                evaluation
                            ),
                            db_path=incident_db_path,
                        )
                    )

                    if not isinstance(
                        enqueue_result,
                        dict,
                    ):
                        raise TypeError(
                            "System incident alert enqueue "
                            "result is invalid."
                        )

                    queued = bool(
                        enqueue_result.get(
                            "queued"
                        )
                    )
                except Exception:
                    logger.warning(
                        "System incident alert enqueue failed."
                    )

                if queued:
                    background_tasks.add_task(
                        _run_incident_alert_worker_safely,
                        resolved_incident_alert_worker,
                        incident_alert_settings,
                        incident_db_path,
                    )

        return system_health_payload(
            report
        )

    return router
