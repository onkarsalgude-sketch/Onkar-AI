"""Authenticated, read-only admin dashboard summary API."""

from __future__ import annotations

from typing import Any, Callable

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
from app.services.dashboard_service import (
    build_dashboard_health,
    build_dashboard_summary,
)


DASHBOARD_SUMMARY_PATH = (
    "/admin/dashboard/summary"
)
DASHBOARD_HEALTH_PATH = (
    "/admin/dashboard/health"
)


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
            "Valid dashboard monitoring "
            "authorization is required."
        ),
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def _dashboard_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Dashboard summary is unavailable."
        ),
    )


def _dashboard_health_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Dashboard health is unavailable."
        ),
    )


def create_dashboard_admin_router(
    settings: SystemHealthMonitoringSettings,
    *,
    summary_provider: Callable = (
        build_dashboard_summary
    ),
    health_provider: Callable = (
        build_dashboard_health
    ),
    db_path: str | None = None,
) -> APIRouter:
    """Create authenticated read-only dashboard routes."""

    validate_system_health_monitoring_settings(
        settings
    )

    if not callable(
        summary_provider
    ):
        raise TypeError(
            "Dashboard summary provider must be callable."
        )

    if not callable(
        health_provider
    ):
        raise TypeError(
            "Dashboard health provider must be callable."
        )

    router = APIRouter()

    @router.get(
        DASHBOARD_SUMMARY_PATH,
        operation_id=(
            "get_admin_dashboard_summary"
        ),
        tags=["admin"],
    )
    def get_admin_dashboard_summary(
        request: Request,
    ) -> dict[str, Any]:
        _authenticate(
            request,
            settings,
        )

        try:
            summary = summary_provider(
                db_path=db_path
            )
        except Exception:
            raise _dashboard_unavailable()

        if not isinstance(
            summary,
            dict,
        ):
            raise _dashboard_unavailable()

        return {
            "service": "dashboard",
            "summary": summary,
        }

    @router.get(
        DASHBOARD_HEALTH_PATH,
        operation_id=(
            "get_admin_dashboard_health"
        ),
        tags=["admin"],
    )
    def get_admin_dashboard_health(
        request: Request,
    ) -> dict[str, Any]:
        _authenticate(
            request,
            settings,
        )

        try:
            health = health_provider(
                recovery_report=getattr(
                    request.app.state,
                    "document_recovery_report",
                    None,
                ),
                rag_runtime=getattr(
                    request.app.state,
                    "rag_runtime",
                    None,
                ),
            )
        except Exception:
            raise _dashboard_health_unavailable()

        if not isinstance(
            health,
            dict,
        ):
            raise _dashboard_health_unavailable()

        return {
            "service": "dashboard_health",
            "health": health,
        }

    return router
