"""Persistent and sanitized document-recovery run history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.config.settings import CHAT_DB
from app.database.db import (
    begin_write_transaction,
    get_runtime_connection,
)


DB_PATH = str(CHAT_DB)

DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100
DEFAULT_RETENTION_LIMIT = 100

_ALLOWED_STATUSES = frozenset(
    {
        "disabled",
        "completed",
        "completed_with_failures",
        "skipped_lock_held",
        "failed",
    }
)

_COUNT_FIELDS = (
    "total_examined",
    "candidate_count",
    "processing_recovered_count",
    "deleting_completed_count",
    "failure_count",
    "skipped_count",
    "recent_count",
    "invalid_timestamp_count",
    "deferred_count",
)

_HISTORY_COLUMNS = (
    "run_id",
    "status",
    "recovery_enabled",
    "started_at",
    "finished_at",
    "duration_ms",
    *_COUNT_FIELDS,
)


class DocumentRecoveryHistoryError(
    RuntimeError
):
    """Raised when recovery history cannot be handled safely."""


def _report_value(
    report: Any,
    name: str,
    default: Any = None,
) -> Any:
    if isinstance(report, dict):
        return report.get(
            name,
            default,
        )

    return getattr(
        report,
        name,
        default,
    )


def _normalize_status(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip().casefold()

    if normalized not in _ALLOWED_STATUSES:
        raise DocumentRecoveryHistoryError(
            "Document recovery status is invalid."
        )

    return normalized


def _normalize_nonnegative_integer(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise DocumentRecoveryHistoryError(
            f"{field_name} must be a "
            "non-negative integer."
        )

    try:
        normalized = int(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as error:
        raise DocumentRecoveryHistoryError(
            f"{field_name} must be a "
            "non-negative integer."
        ) from error

    if (
        isinstance(value, float)
        and not value.is_integer()
    ):
        raise DocumentRecoveryHistoryError(
            f"{field_name} must be a "
            "non-negative integer."
        )

    if normalized < 0:
        raise DocumentRecoveryHistoryError(
            f"{field_name} must be a "
            "non-negative integer."
        )

    return normalized


def _normalize_limit(
    value: Any,
    *,
    maximum: int,
    field_name: str,
) -> int:
    normalized = _normalize_nonnegative_integer(
        value,
        field_name=field_name,
    )

    if (
        normalized < 1
        or normalized > maximum
    ):
        raise DocumentRecoveryHistoryError(
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
            normalized = (
                datetime.fromisoformat(
                    candidate
                )
            )
        except ValueError as error:
            raise DocumentRecoveryHistoryError(
                f"{field_name} must be a "
                "valid ISO-8601 timestamp."
            ) from error
    else:
        raise DocumentRecoveryHistoryError(
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


def _timestamp_value(
    value: str,
) -> datetime:
    return datetime.fromisoformat(
        value
    )


def _normalize_run_id(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip()

    if not normalized:
        raise DocumentRecoveryHistoryError(
            "Document recovery run ID is invalid."
        )

    return normalized


def _build_record(
    report: Any,
    *,
    started_at: datetime | str,
    finished_at: datetime | str,
    duration_ms: Any,
    run_id_factory: Callable[[], Any],
) -> dict:
    normalized_started_at = (
        _normalize_timestamp(
            started_at,
            field_name="started_at",
        )
    )

    normalized_finished_at = (
        _normalize_timestamp(
            finished_at,
            field_name="finished_at",
        )
    )

    if (
        _timestamp_value(
            normalized_finished_at
        )
        < _timestamp_value(
            normalized_started_at
        )
    ):
        raise DocumentRecoveryHistoryError(
            "finished_at cannot be earlier "
            "than started_at."
        )

    record = {
        "run_id": _normalize_run_id(
            run_id_factory()
        ),
        "status": _normalize_status(
            _report_value(
                report,
                "status",
                "",
            )
        ),
        "recovery_enabled": (
            1
            if bool(
                _report_value(
                    report,
                    "enabled",
                    False,
                )
            )
            else 0
        ),
        "started_at": normalized_started_at,
        "finished_at": normalized_finished_at,
        "duration_ms": (
            _normalize_nonnegative_integer(
                duration_ms,
                field_name="duration_ms",
            )
        ),
    }

    for field_name in _COUNT_FIELDS:
        record[field_name] = (
            _normalize_nonnegative_integer(
                _report_value(
                    report,
                    field_name,
                    0,
                ),
                field_name=field_name,
            )
        )

    return record


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


def _row_value(
    row: Any,
    index: int,
    name: str,
) -> Any:
    try:
        return row[name]
    except (
        KeyError,
        IndexError,
        TypeError,
    ):
        return row[index]


def _row_to_record(
    row: Any,
) -> dict:
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

    values["recovery_enabled"] = bool(
        int(
            values[
                "recovery_enabled"
            ]
        )
    )

    values["duration_ms"] = int(
        values["duration_ms"]
    )

    for field_name in _COUNT_FIELDS:
        values[field_name] = int(
            values[field_name]
        )

    return values


def record_document_recovery_run(
    report: Any,
    *,
    started_at: datetime | str,
    finished_at: datetime | str,
    duration_ms: Any,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    run_id_factory: Callable[[], Any] = uuid4,
    retention_limit: int = (
        DEFAULT_RETENTION_LIMIT
    ),
) -> dict:
    """Persist one sanitized run and prune old rows atomically."""
    normalized_retention_limit = (
        _normalize_limit(
            retention_limit,
            maximum=MAX_HISTORY_LIMIT,
            field_name="retention_limit",
        )
    )

    record = _build_record(
        report,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        run_id_factory=run_id_factory,
    )

    resolved_db_path = (
        DB_PATH
        if db_path is None
        else str(db_path)
    )

    connection = None

    try:
        connection = connection_factory(
            resolved_db_path
        )

        cursor = connection.cursor()

        begin_write_transaction(
            connection
        )

        cursor.execute(
            """
            INSERT INTO document_recovery_runs (
                run_id,
                status,
                recovery_enabled,
                started_at,
                finished_at,
                duration_ms,
                total_examined,
                candidate_count,
                processing_recovered_count,
                deleting_completed_count,
                failure_count,
                skipped_count,
                recent_count,
                invalid_timestamp_count,
                deferred_count
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            tuple(
                record[column_name]
                for column_name
                in _HISTORY_COLUMNS
            ),
        )

        cursor.execute(
            """
            DELETE FROM document_recovery_runs
            WHERE run_id NOT IN (
                SELECT run_id
                FROM document_recovery_runs
                ORDER BY
                    finished_at DESC,
                    run_id DESC
                LIMIT ?
            )
            """,
            (
                normalized_retention_limit,
            ),
        )

        connection.commit()

        return dict(record)
    except DocumentRecoveryHistoryError:
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

        raise DocumentRecoveryHistoryError(
            "Document recovery history "
            "write failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def list_document_recovery_runs(
    limit: int = DEFAULT_HISTORY_LIMIT,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> list[dict]:
    """Return sanitized recovery runs newest first."""
    normalized_limit = _normalize_limit(
        limit,
        maximum=MAX_HISTORY_LIMIT,
        field_name="limit",
    )

    resolved_db_path = (
        DB_PATH
        if db_path is None
        else str(db_path)
    )

    connection = None

    try:
        connection = connection_factory(
            resolved_db_path
        )

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                run_id,
                status,
                recovery_enabled,
                started_at,
                finished_at,
                duration_ms,
                total_examined,
                candidate_count,
                processing_recovered_count,
                deleting_completed_count,
                failure_count,
                skipped_count,
                recent_count,
                invalid_timestamp_count,
                deferred_count
            FROM document_recovery_runs
            ORDER BY
                finished_at DESC,
                run_id DESC
            LIMIT ?
            """,
            (
                normalized_limit,
            ),
        )

        return [
            _row_to_record(row)
            for row in cursor.fetchall()
        ]
    except DocumentRecoveryHistoryError:
        raise
    except Exception as error:
        raise DocumentRecoveryHistoryError(
            "Document recovery history "
            "read failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def summarize_document_recovery_runs(
    limit: int = MAX_HISTORY_LIMIT,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> dict:
    """Summarize a bounded set of recent recovery runs."""
    runs = list_document_recovery_runs(
        limit,
        db_path=db_path,
        connection_factory=connection_factory,
    )

    status_counts = {
        status: 0
        for status in sorted(
            _ALLOWED_STATUSES
        )
    }

    total_failures = 0
    failure_runs = 0
    duration_total = 0

    for run in runs:
        status = run["status"]

        status_counts[status] += 1

        failure_count = int(
            run["failure_count"]
        )

        total_failures += failure_count

        if (
            failure_count > 0
            or status
            in {
                "failed",
                "completed_with_failures",
            }
        ):
            failure_runs += 1

        duration_total += int(
            run["duration_ms"]
        )

    total_runs = len(runs)

    average_duration_ms = (
        round(
            duration_total
            / total_runs,
            2,
        )
        if total_runs
        else 0.0
    )

    return {
        "total_runs": total_runs,
        "status_counts": status_counts,
        "failure_runs": failure_runs,
        "total_failures": total_failures,
        "average_duration_ms": (
            average_duration_ms
        ),
        "latest_run": (
            runs[0]
            if runs
            else None
        ),
    }
