"""Authenticated, read-only document recovery monitoring API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config.document_recovery_monitoring import (
    DocumentRecoveryMonitoringSettings,
    validate_document_recovery_monitoring_settings,
)
from app.services.branch_merge_security import (
    verify_branch_merge_bearer,
)


_STATUS_PATH = (
    "/admin/document-recovery/status"
)


def _report_value(
    report: Any,
    name: str,
    default: Any,
) -> Any:
    if isinstance(report, Mapping):
        return report.get(
            name,
            default,
        )

    return getattr(
        report,
        name,
        default,
    )


def _safe_count(
    report: Any,
    name: str,
) -> int:
    try:
        return max(
            0,
            int(
                _report_value(
                    report,
                    name,
                    0,
                )
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _initializing_payload() -> dict:
    return {
        "service": "document_recovery",
        "status": "initializing",
        "ready": False,
        "healthy": False,
        "attention_required": False,
        "recovery_enabled": None,
        "counts": {
            "total_examined": 0,
            "candidates": 0,
            "processing_recovered": 0,
            "deleting_completed": 0,
            "failures": 0,
            "skipped": 0,
            "recent": 0,
            "invalid_timestamps": 0,
            "deferred": 0,
        },
    }


def _report_payload(
    report: Any,
) -> dict:
    status = str(
        _report_value(
            report,
            "status",
            "unknown",
        )
    ).strip().casefold()

    failure_count = _safe_count(
        report,
        "failure_count",
    )

    healthy = (
        status in {
            "completed",
            "disabled",
        }
        and failure_count == 0
    )

    return {
        "service": "document_recovery",
        "status": status,
        "ready": True,
        "healthy": healthy,
        "attention_required": not healthy,
        "recovery_enabled": bool(
            _report_value(
                report,
                "enabled",
                False,
            )
        ),
        "counts": {
            "total_examined": _safe_count(
                report,
                "total_examined",
            ),
            "candidates": _safe_count(
                report,
                "candidate_count",
            ),
            "processing_recovered": _safe_count(
                report,
                "processing_recovered_count",
            ),
            "deleting_completed": _safe_count(
                report,
                "deleting_completed_count",
            ),
            "failures": failure_count,
            "skipped": _safe_count(
                report,
                "skipped_count",
            ),
            "recent": _safe_count(
                report,
                "recent_count",
            ),
            "invalid_timestamps": _safe_count(
                report,
                "invalid_timestamp_count",
            ),
            "deferred": _safe_count(
                report,
                "deferred_count",
            ),
        },
    }


def create_document_recovery_admin_router(
    settings: DocumentRecoveryMonitoringSettings,
) -> APIRouter:
    validate_document_recovery_monitoring_settings(
        settings
    )

    router = APIRouter()

    @router.get(
        _STATUS_PATH,
        operation_id=(
            "get_document_recovery_status"
        ),
        tags=["admin"],
    )
    async def get_document_recovery_status(
        request: Request,
    ) -> dict:
        authenticated = (
            verify_branch_merge_bearer(
                request.headers.get(
                    "authorization"
                ),
                settings.token_sha256,
            )
        )

        if not authenticated:
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

        report = getattr(
            request.app.state,
            "document_recovery_report",
            None,
        )

        if report is None:
            return _initializing_payload()

        return _report_payload(
            report
        )

    return router
