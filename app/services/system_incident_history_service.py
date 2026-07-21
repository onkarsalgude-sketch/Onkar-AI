"""Durable, sanitized system-incident lifecycle persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.config.settings import CHAT_DB
from app.database.db import (
    begin_write_transaction,
    get_runtime_connection,
)
from app.services.system_health_service import SystemHealthReport
from app.services.system_incident_service import (
    IncidentReconciliation,
    IncidentSignal,
    incident_reconciliation_payload,
    reconcile_incident_signals,
)


DB_PATH = str(CHAT_DB)

DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100
DEFAULT_RETENTION_LIMIT = 100

_ALLOWED_STATES = {
    "open",
    "resolved",
}

_HISTORY_COLUMNS = (
    "incident_id",
    "incident_key",
    "component",
    "severity",
    "source_status",
    "detail",
    "critical",
    "state",
    "fingerprint",
    "opened_at",
    "last_seen_at",
    "resolved_at",
    "occurrence_count",
)


class SystemIncidentHistoryError(RuntimeError):
    """Raised when incident lifecycle history cannot be handled safely."""


def _normalize_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise SystemIncidentHistoryError(
            f"{field_name} must be an integer."
        )

    try:
        normalized = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentHistoryError(
            f"{field_name} must be an integer."
        ) from error

    return normalized


def _normalize_limit(
    value: Any,
    *,
    maximum: int,
    field_name: str,
) -> int:
    normalized = _normalize_integer(
        value,
        field_name=field_name,
    )

    if (
        normalized < 1
        or normalized > maximum
    ):
        raise SystemIncidentHistoryError(
            f"{field_name} must be between "
            f"1 and {maximum}."
        )

    return normalized


def _normalize_timestamp(
    value: Any,
    *,
    field_name: str,
) -> str:
    if isinstance(value, datetime):
        normalized = value
    elif isinstance(value, str):
        candidate = value.strip()

        if candidate.endswith("Z"):
            candidate = (
                candidate[:-1]
                + "+00:00"
            )

        try:
            normalized = datetime.fromisoformat(
                candidate
            )
        except ValueError as error:
            raise SystemIncidentHistoryError(
                f"{field_name} must be a "
                "valid ISO-8601 timestamp."
            ) from error
    else:
        raise SystemIncidentHistoryError(
            f"{field_name} must be a "
            "datetime or ISO-8601 string."
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


def _normalize_state(
    value: Any,
    *,
    allow_none: bool,
) -> str | None:
    if value is None and allow_none:
        return None

    normalized = str(
        value
    ).strip().casefold()

    if normalized not in _ALLOWED_STATES:
        raise SystemIncidentHistoryError(
            "Incident state is invalid."
        )

    return normalized


def _normalize_incident_id(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip()

    if (
        not normalized
        or len(normalized) > 128
    ):
        raise SystemIncidentHistoryError(
            "Incident identifier is invalid."
        )

    return normalized


def _row_value(
    row: Any,
    index: int,
    name: str,
) -> Any:
    try:
        return row[name]
    except (
        KeyError,
        TypeError,
        IndexError,
    ):
        try:
            return row[index]
        except (
            KeyError,
            TypeError,
            IndexError,
        ) as error:
            raise SystemIncidentHistoryError(
                "Incident history row is invalid."
            ) from error


def _row_to_record(
    row: Any,
) -> dict[str, Any]:
    values = {
        name: _row_value(
            row,
            index,
            name,
        )
        for index, name in enumerate(
            _HISTORY_COLUMNS
        )
    }

    values["critical"] = bool(
        int(
            values["critical"]
        )
    )

    values["occurrence_count"] = int(
        values["occurrence_count"]
    )

    values["state"] = _normalize_state(
        values["state"],
        allow_none=False,
    )

    return values


def _record_to_signal(
    record: dict[str, Any],
) -> IncidentSignal:
    signal = IncidentSignal(
        incident_key=record[
            "incident_key"
        ],
        component=record["component"],
        severity=record["severity"],
        source_status=record[
            "source_status"
        ],
        detail=record["detail"],
        critical=record["critical"],
    )

    if signal.fingerprint != str(
        record["fingerprint"]
    ).strip().casefold():
        raise SystemIncidentHistoryError(
            "Stored incident fingerprint is invalid."
        )

    return signal


def _safe_rollback(
    connection: Any,
) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _safe_close(
    connection: Any,
) -> None:
    try:
        connection.close()
    except Exception:
        pass


def _resolved_db_path(
    db_path: str | None,
) -> str:
    return (
        DB_PATH
        if db_path is None
        else str(db_path)
    )


def _select_incident_rows(
    cursor: Any,
    *,
    state: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    columns = ",\n                ".join(
        _HISTORY_COLUMNS
    )

    if state is None:
        cursor.execute(
            f"""
            SELECT
                {columns}
            FROM system_incidents
            ORDER BY
                last_seen_at DESC,
                incident_id DESC
            LIMIT ?
            """,
            (
                limit,
            ),
        )
    else:
        cursor.execute(
            f"""
            SELECT
                {columns}
            FROM system_incidents
            WHERE state = ?
            ORDER BY
                last_seen_at DESC,
                incident_id DESC
            LIMIT ?
            """,
            (
                state,
                limit,
            ),
        )

    return [
        _row_to_record(row)
        for row in cursor.fetchall()
    ]


def _load_open_records(
    cursor: Any,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[IncidentSignal, ...],
]:
    columns = ",\n                ".join(
        _HISTORY_COLUMNS
    )

    cursor.execute(
        f"""
        SELECT
            {columns}
        FROM system_incidents
        WHERE state = 'open'
        ORDER BY
            incident_key ASC,
            opened_at ASC,
            incident_id ASC
        """
    )

    records = tuple(
        _row_to_record(row)
        for row in cursor.fetchall()
    )

    seen_keys: set[str] = set()
    signals: list[IncidentSignal] = []

    for record in records:
        incident_key = str(
            record["incident_key"]
        )

        if incident_key in seen_keys:
            raise SystemIncidentHistoryError(
                "Multiple open incident lifecycles "
                "exist for one incident key."
            )

        seen_keys.add(
            incident_key
        )

        signals.append(
            _record_to_signal(
                record
            )
        )

    return (
        records,
        tuple(signals),
    )


def load_open_incident_signals(
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> tuple[IncidentSignal, ...]:
    """Load current open incident signals from durable history."""
    connection = None

    try:
        connection = connection_factory(
            _resolved_db_path(
                db_path
            )
        )

        cursor = connection.cursor()

        _, signals = _load_open_records(
            cursor
        )

        return signals
    except SystemIncidentHistoryError:
        raise
    except Exception as error:
        raise SystemIncidentHistoryError(
            "System incident history read failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def record_system_incident_evaluation(
    report: SystemHealthReport,
    *,
    observed_at: datetime | str,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    incident_id_factory: Callable[[], Any] = uuid4,
    retention_limit: int = (
        DEFAULT_RETENTION_LIMIT
    ),
) -> dict[str, Any]:
    """Persist one health evaluation as atomic incident transitions."""
    normalized_observed_at = _normalize_timestamp(
        observed_at,
        field_name="observed_at",
    )

    normalized_retention_limit = _normalize_limit(
        retention_limit,
        maximum=MAX_HISTORY_LIMIT,
        field_name="retention_limit",
    )

    connection = None

    try:
        connection = connection_factory(
            _resolved_db_path(
                db_path
            )
        )

        cursor = connection.cursor()

        begin_write_transaction(
            connection
        )

        (
            open_records,
            previous_signals,
        ) = _load_open_records(
            cursor
        )

        open_record_by_key = {
            str(
                record["incident_key"]
            ): record
            for record in open_records
        }

        for record in open_records:
            if (
                normalized_observed_at
                < str(
                    record["last_seen_at"]
                )
            ):
                raise SystemIncidentHistoryError(
                    "Incident observation timestamp "
                    "cannot move backwards."
                )

        reconciliation = (
            reconcile_incident_signals(
                previous_signals,
                report,
            )
        )

        for signal in reconciliation.opened:
            incident_id = _normalize_incident_id(
                incident_id_factory()
            )

            cursor.execute(
                """
                INSERT INTO system_incidents (
                    incident_id,
                    incident_key,
                    component,
                    severity,
                    source_status,
                    detail,
                    critical,
                    state,
                    fingerprint,
                    opened_at,
                    last_seen_at,
                    resolved_at,
                    occurrence_count
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    'open', ?, ?, ?, NULL, 1
                )
                """,
                (
                    incident_id,
                    signal.incident_key,
                    signal.component,
                    signal.severity,
                    signal.source_status,
                    signal.detail,
                    int(
                        signal.critical
                    ),
                    signal.fingerprint,
                    normalized_observed_at,
                    normalized_observed_at,
                ),
            )

        observed_signals = (
            *reconciliation.updated,
            *reconciliation.unchanged,
        )

        for signal in observed_signals:
            record = open_record_by_key.get(
                signal.incident_key
            )

            if record is None:
                raise SystemIncidentHistoryError(
                    "Open incident lifecycle is missing."
                )

            cursor.execute(
                """
                UPDATE system_incidents
                SET
                    component = ?,
                    severity = ?,
                    source_status = ?,
                    detail = ?,
                    critical = ?,
                    fingerprint = ?,
                    last_seen_at = ?,
                    occurrence_count = (
                        occurrence_count + 1
                    )
                WHERE
                    incident_id = ?
                    AND state = 'open'
                """,
                (
                    signal.component,
                    signal.severity,
                    signal.source_status,
                    signal.detail,
                    int(
                        signal.critical
                    ),
                    signal.fingerprint,
                    normalized_observed_at,
                    record["incident_id"],
                ),
            )

            if int(
                cursor.rowcount
            ) != 1:
                raise SystemIncidentHistoryError(
                    "Open incident lifecycle update failed."
                )

        for signal in reconciliation.resolved:
            record = open_record_by_key.get(
                signal.incident_key
            )

            if record is None:
                raise SystemIncidentHistoryError(
                    "Resolved incident lifecycle is missing."
                )

            cursor.execute(
                """
                UPDATE system_incidents
                SET
                    state = 'resolved',
                    resolved_at = ?
                WHERE
                    incident_id = ?
                    AND state = 'open'
                """,
                (
                    normalized_observed_at,
                    record["incident_id"],
                ),
            )

            if int(
                cursor.rowcount
            ) != 1:
                raise SystemIncidentHistoryError(
                    "Incident resolution update failed."
                )

        cursor.execute(
            """
            DELETE FROM system_incidents
            WHERE
                state = 'resolved'
                AND incident_id NOT IN (
                    SELECT incident_id
                    FROM system_incidents
                    WHERE state = 'resolved'
                    ORDER BY
                        resolved_at DESC,
                        incident_id DESC
                    LIMIT ?
                )
            """,
            (
                normalized_retention_limit,
            ),
        )

        connection.commit()

        payload = (
            incident_reconciliation_payload(
                reconciliation
            )
        )

        return {
            **payload,
            "observed_at": (
                normalized_observed_at
            ),
            "retention_limit": (
                normalized_retention_limit
            ),
        }
    except SystemIncidentHistoryError:
        if connection is not None:
            _safe_rollback(
                connection
            )

        raise
    except Exception as error:
        if connection is not None:
            _safe_rollback(
                connection
            )

        raise SystemIncidentHistoryError(
            "System incident history write failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def list_system_incidents(
    limit: int = DEFAULT_HISTORY_LIMIT,
    *,
    state: str | None = None,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> list[dict[str, Any]]:
    """Return bounded sanitized incident lifecycles newest first."""
    normalized_limit = _normalize_limit(
        limit,
        maximum=MAX_HISTORY_LIMIT,
        field_name="limit",
    )

    normalized_state = _normalize_state(
        state,
        allow_none=True,
    )

    connection = None

    try:
        connection = connection_factory(
            _resolved_db_path(
                db_path
            )
        )

        cursor = connection.cursor()

        return _select_incident_rows(
            cursor,
            state=normalized_state,
            limit=normalized_limit,
        )
    except SystemIncidentHistoryError:
        raise
    except Exception as error:
        raise SystemIncidentHistoryError(
            "System incident history read failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def summarize_system_incidents(
    limit: int = MAX_HISTORY_LIMIT,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> dict[str, Any]:
    """Summarize a bounded set of recent incident lifecycles."""
    incidents = list_system_incidents(
        limit,
        db_path=db_path,
        connection_factory=connection_factory,
    )

    active = [
        incident
        for incident in incidents
        if incident["state"] == "open"
    ]

    resolved = [
        incident
        for incident in incidents
        if incident["state"] == "resolved"
    ]

    active_warning_count = sum(
        incident["severity"] == "warning"
        for incident in active
    )

    active_critical_count = sum(
        incident["severity"] == "critical"
        for incident in active
    )

    total_occurrences = sum(
        int(
            incident["occurrence_count"]
        )
        for incident in incidents
    )

    return {
        "total_incidents": len(
            incidents
        ),
        "active_count": len(
            active
        ),
        "resolved_count": len(
            resolved
        ),
        "active_warning_count": (
            active_warning_count
        ),
        "active_critical_count": (
            active_critical_count
        ),
        "has_active_critical": (
            active_critical_count > 0
        ),
        "total_occurrences": (
            total_occurrences
        ),
        "latest_incident": (
            incidents[0]
            if incidents
            else None
        ),
    }
