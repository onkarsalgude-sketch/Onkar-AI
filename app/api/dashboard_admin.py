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
    build_dashboard_summary,
)


DASHBOARD_SUMMARY_PATH = (
    "/admin/dashboard/summary"
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


def create_dashboard_admin_router(
    settings: SystemHealthMonitoringSettings,
    *,
    summary_provider: Callable = (
        build_dashboard_summary
    ),
    db_path: str | None = None,
) -> APIRouter:
    """Create the authenticated read-only dashboard summary route."""

    validate_system_health_monitoring_settings(
        settings
    )

    if not callable(
        summary_provider
    ):
        raise TypeError(
            "Dashboard summary provider must be callable."
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

    return router
