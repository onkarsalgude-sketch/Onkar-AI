"""Concrete, sanitized system-health component probes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.config.database import (
    load_database_settings,
)
from app.config.storage import (
    load_document_storage_settings,
)
from app.database.engine import (
    build_database_engine,
)
from app.services.document_object_service import (
    get_document_storage,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    HealthCheckOutcome,
    SystemHealthConfigurationError,
    degraded_outcome,
    disabled_outcome,
    healthy_outcome,
    unavailable_outcome,
)


SYSTEM_HEALTH_STORAGE_PROBE_KEY = (
    "_system_health/readiness_probe"
)

_HEALTHY_RECOVERY_STATUSES = {
    "completed",
    "skipped_lock_held",
}


def _boolean_setting(
    value: Any,
    attribute: str,
) -> bool:
    candidate = getattr(
        value,
        attribute,
        False,
    )

    if callable(
        candidate
    ):
        candidate = candidate()

    return bool(
        candidate
    )


def _safe_nonnegative_integer(
    value: Any,
) -> int:
    try:
        normalized = int(
            value
        )
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


def check_database_health(
    *,
    settings_loader: Callable = (
        load_database_settings
    ),
    engine_builder: Callable = (
        build_database_engine
    ),
) -> HealthCheckOutcome:
    """Verify database connectivity with a read-only SELECT."""

    engine = None

    try:
        settings = settings_loader()

        is_postgresql = _boolean_setting(
            settings,
            "is_postgresql",
        )

        is_sqlite = _boolean_setting(
            settings,
            "is_sqlite",
        )

        if not (
            is_postgresql
            or is_sqlite
        ):
            return unavailable_outcome(
                "database_backend_invalid"
            )

        engine = engine_builder(
            settings
        )

        with engine.connect() as connection:
            result = connection.exec_driver_sql(
                "SELECT 1"
            )

            value = result.scalar_one()

        if int(value) != 1:
            return unavailable_outcome(
                "database_response_invalid"
            )

        detail = (
            "postgresql_reachable"
            if is_postgresql
            else "sqlite_reachable"
        )

        return healthy_outcome(
            detail
        )
    except Exception:
        return unavailable_outcome(
            "database_unreachable"
        )
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


def check_document_storage_health(
    *,
    settings_loader: Callable = (
        load_document_storage_settings
    ),
    storage_loader: Callable = (
        get_document_storage
    ),
    probe_key: str = (
        SYSTEM_HEALTH_STORAGE_PROBE_KEY
    ),
) -> HealthCheckOutcome:
    """Perform a non-mutating storage existence request."""

    try:
        settings = settings_loader()

        is_r2 = _boolean_setting(
            settings,
            "is_r2",
        )

        is_local = _boolean_setting(
            settings,
            "is_local",
        )

        if not (
            is_r2
            or is_local
        ):
            return unavailable_outcome(
                "storage_backend_invalid"
            )

        storage = storage_loader()

        exists_method = getattr(
            storage,
            "exists",
            None,
        )

        if not callable(
            exists_method
        ):
            return unavailable_outcome(
                "storage_interface_invalid"
            )

        exists_method(
            probe_key
        )

        detail = (
            "r2_reachable"
            if is_r2
            else "local_storage_reachable"
        )

        return healthy_outcome(
            detail
        )
    except Exception:
        return unavailable_outcome(
            "storage_unreachable"
        )


def check_document_recovery_health(
    report: Any,
) -> HealthCheckOutcome:
    """Translate the startup recovery report into health state."""

    if report is None:
        return degraded_outcome(
            "recovery_initializing"
        )

    status = str(
        getattr(
            report,
            "status",
            "unknown",
        )
    ).strip().casefold()

    enabled_value = getattr(
        report,
        "enabled",
        getattr(
            report,
            "recovery_enabled",
            False,
        ),
    )

    enabled = bool(
        enabled_value
    )

    failure_count = _safe_nonnegative_integer(
        getattr(
            report,
            "failure_count",
            0,
        )
    )

    if (
        not enabled
        or status == "disabled"
    ):
        return disabled_outcome(
            "recovery_disabled"
        )

    if status == "failed":
        return unavailable_outcome(
            "recovery_failed"
        )

    if (
        status == "completed_with_failures"
        or failure_count > 0
    ):
        return degraded_outcome(
            "recovery_failures"
        )

    if status in _HEALTHY_RECOVERY_STATUSES:
        detail = (
            "recovery_lock_held"
            if status == "skipped_lock_held"
            else "recovery_completed"
        )

        return healthy_outcome(
            detail
        )

    return degraded_outcome(
        "recovery_status_unknown"
    )


def build_default_health_check_definitions(
    *,
    recovery_report_provider: Callable[
        [],
        Any,
    ],
    database_check: Callable[
        [],
        HealthCheckOutcome,
    ] = check_database_health,
    storage_check: Callable[
        [],
        HealthCheckOutcome,
    ] = check_document_storage_health,
) -> tuple[
    HealthCheckDefinition,
    ...,
]:
    """Build stable system-health definitions in display order."""

    if not callable(
        recovery_report_provider
    ):
        raise SystemHealthConfigurationError(
            "Recovery report provider must be callable."
        )

    if not callable(
        database_check
    ):
        raise SystemHealthConfigurationError(
            "Database health check must be callable."
        )

    if not callable(
        storage_check
    ):
        raise SystemHealthConfigurationError(
            "Storage health check must be callable."
        )

    return (
        HealthCheckDefinition(
            name="database",
            check=database_check,
            critical=True,
        ),
        HealthCheckDefinition(
            name="document_storage",
            check=storage_check,
            critical=True,
        ),
        HealthCheckDefinition(
            name="document_recovery",
            check=lambda: (
                check_document_recovery_health(
                    recovery_report_provider()
                )
            ),
            critical=False,
        ),
    )
