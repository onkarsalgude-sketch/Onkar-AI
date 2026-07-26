"""Read-only aggregate metrics for the admin dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from app.config.settings import CHAT_DB
from app.database.db import get_runtime_connection
from app.services.document_recovery_history_service import (
    MAX_HISTORY_LIMIT as RECOVERY_HISTORY_LIMIT,
    summarize_document_recovery_runs,
)
from app.services.system_health_checks import (
    build_default_health_check_definitions,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    SystemHealthReport,
    healthy_outcome,
    run_system_health_checks,
    system_health_payload,
    unavailable_outcome,
)
from app.services.system_incident_history_service import (
    MAX_HISTORY_LIMIT as INCIDENT_HISTORY_LIMIT,
    summarize_system_incidents,
)


DB_PATH = str(CHAT_DB)
MAX_AGENT_USAGE_ROWS = 25


class DashboardMetricsError(RuntimeError):
    """Raised when dashboard metrics cannot be read safely."""


def _safe_close(connection: Any) -> None:
    try:
        connection.close()
    except Exception:
        pass


def _safe_nonnegative_integer(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0

    return max(0, normalized)


def _resolved_db_path(
    db_path: str | None,
) -> str:
    return (
        DB_PATH
        if db_path is None
        else str(db_path)
    )


def _rag_runtime_outcome(
    rag_runtime: Any,
):
    if rag_runtime is None:
        return unavailable_outcome(
            "rag_runtime_unavailable"
        )

    settings = getattr(
        rag_runtime,
        "settings",
        None,
    )

    if settings is None:
        return unavailable_outcome(
            "rag_runtime_invalid"
        )

    return healthy_outcome(
        "rag_runtime_ready"
    )


def build_dashboard_health(
    *,
    recovery_report: Any = None,
    rag_runtime: Any = None,
    definitions_builder: Callable = (
        build_default_health_check_definitions
    ),
    health_runner: Callable = (
        run_system_health_checks
    ),
) -> dict[str, Any]:
    """Return live health without recording incidents or alerts."""

    try:
        definitions = tuple(
            definitions_builder(
                recovery_report_provider=(
                    lambda: recovery_report
                )
            )
        )

        definitions = definitions + (
            HealthCheckDefinition(
                name="knowledge_rag",
                check=lambda: (
                    _rag_runtime_outcome(
                        rag_runtime
                    )
                ),
                critical=False,
            ),
        )

        report = health_runner(
            definitions
        )

        if not isinstance(
            report,
            SystemHealthReport,
        ):
            raise TypeError(
                "Dashboard health runner returned an invalid report."
            )

        payload = system_health_payload(
            report
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Dashboard health payload is invalid."
            )

        return payload
    except DashboardMetricsError:
        raise
    except Exception as error:
        raise DashboardMetricsError(
            "Dashboard health metrics are unavailable."
        ) from error


def summarize_usage_metrics(
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
) -> dict[str, Any]:
    """Return bounded aggregate counts from current chat data."""

    connection = None

    try:
        connection = connection_factory(
            _resolved_db_path(db_path)
        )
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM chats),
                (SELECT COUNT(*) FROM messages),
                (
                    SELECT COUNT(*)
                    FROM messages
                    WHERE role = 'user'
                ),
                (
                    SELECT COUNT(*)
                    FROM messages
                    WHERE role = 'assistant'
                ),
                (
                    SELECT COUNT(*)
                    FROM messages
                    WHERE role = 'assistant'
                      AND agent_id IS NOT NULL
                      AND TRIM(agent_id) <> ''
                ),
                (SELECT COUNT(*) FROM documents),
                (
                    SELECT COALESCE(
                        SUM(file_size),
                        0
                    )
                    FROM documents
                ),
                (
                    SELECT COUNT(*)
                    FROM documents
                    WHERE status = 'ready'
                )
            """
        )

        row = cursor.fetchone()

        if row is None or len(row) < 8:
            raise DashboardMetricsError(
                "Dashboard usage metrics are unavailable."
            )

        cursor.execute(
            f"""
            SELECT
                agent_id,
                COUNT(*)
            FROM messages
            WHERE role = 'assistant'
              AND agent_id IS NOT NULL
              AND TRIM(agent_id) <> ''
            GROUP BY agent_id
            ORDER BY
                COUNT(*) DESC,
                agent_id ASC
            LIMIT {MAX_AGENT_USAGE_ROWS}
            """
        )

        agent_usage = []

        for agent_row in cursor.fetchall():
            if (
                agent_row is None
                or len(agent_row) < 2
            ):
                continue

            agent_id = str(
                agent_row[0] or ""
            ).strip()

            if not agent_id:
                continue

            agent_usage.append(
                {
                    "agent_id": agent_id,
                    "message_count": (
                        _safe_nonnegative_integer(
                            agent_row[1]
                        )
                    ),
                }
            )

        document_bytes = (
            _safe_nonnegative_integer(
                row[6]
            )
        )

        return {
            "chats": {
                "total": (
                    _safe_nonnegative_integer(
                        row[0]
                    )
                ),
            },
            "messages": {
                "total": (
                    _safe_nonnegative_integer(
                        row[1]
                    )
                ),
                "user": (
                    _safe_nonnegative_integer(
                        row[2]
                    )
                ),
                "assistant": (
                    _safe_nonnegative_integer(
                        row[3]
                    )
                ),
            },
            "agents": {
                "assistant_messages_with_agent": (
                    _safe_nonnegative_integer(
                        row[4]
                    )
                ),
                "usage": agent_usage,
            },
            "documents": {
                "total": (
                    _safe_nonnegative_integer(
                        row[5]
                    )
                ),
                "ready": (
                    _safe_nonnegative_integer(
                        row[7]
                    )
                ),
            },
            "storage": {
                "document_bytes": (
                    document_bytes
                ),
            },
        }
    except DashboardMetricsError:
        raise
    except Exception as error:
        raise DashboardMetricsError(
            "Dashboard usage metrics are unavailable."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def _optional_section(
    summarizer: Callable,
    limit: int,
    *,
    db_path: str | None,
    connection_factory: Callable,
) -> dict[str, Any]:
    try:
        metrics = summarizer(
            limit,
            db_path=db_path,
            connection_factory=(
                connection_factory
            ),
        )
    except Exception:
        return {
            "available": False,
            "metrics": None,
        }

    if not isinstance(
        metrics,
        dict,
    ):
        return {
            "available": False,
            "metrics": None,
        }

    return {
        "available": True,
        "metrics": metrics,
    }


def build_dashboard_summary(
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    recovery_summarizer: Callable = (
        summarize_document_recovery_runs
    ),
    incident_summarizer: Callable = (
        summarize_system_incidents
    ),
) -> dict[str, Any]:
    """Build a sanitized dashboard summary without creating new state."""

    usage = summarize_usage_metrics(
        db_path=db_path,
        connection_factory=(
            connection_factory
        ),
    )

    recovery = _optional_section(
        recovery_summarizer,
        RECOVERY_HISTORY_LIMIT,
        db_path=db_path,
        connection_factory=(
            connection_factory
        ),
    )

    incidents = _optional_section(
        incident_summarizer,
        INCIDENT_HISTORY_LIMIT,
        db_path=db_path,
        connection_factory=(
            connection_factory
        ),
    )

    return {
        "usage": usage,
        "recovery": recovery,
        "incidents": incidents,
    }


def summarize_today_conversation_activity(
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Return today's conversation activity counts and 4-hour buckets based on message timestamps."""

    connection = None
    try:
        if now_provider is not None:
            now = now_provider()
        else:
            now = datetime.now()

        if not isinstance(now, datetime):
            raise TypeError("now_provider must return a datetime instance.")

        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0)
        end_exclusive_dt = start_dt + timedelta(days=1)

        day_str = start_dt.strftime("%Y-%m-%d")
        start_iso = start_dt.isoformat()
        end_exclusive_iso = end_exclusive_dt.isoformat()

        bucket_intervals = []
        buckets = []
        for i in range(6):
            b_start_dt = start_dt + timedelta(hours=i * 4)
            b_end_dt = start_dt + timedelta(hours=(i + 1) * 4)
            b_start_label = b_start_dt.strftime("%H:%M")
            b_end_label = (
                "24:00" if i == 5 else b_end_dt.strftime("%H:%M")
            )
            bucket_intervals.append((b_start_dt, b_end_dt))
            buckets.append(
                {
                    "label": f"{b_start_label}-{b_end_label}",
                    "start": b_start_dt.isoformat(),
                    "end_exclusive": b_end_dt.isoformat(),
                    "message_count": 0,
                }
            )

        connection = connection_factory(
            _resolved_db_path(db_path)
        )
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT role, created_at
            FROM messages
            WHERE created_at >= ? AND created_at < ?
            """,
            (start_iso, end_exclusive_iso),
        )

        rows = cursor.fetchall()

        total = 0
        user = 0
        assistant = 0
        other = 0

        for row in rows:
            if (
                row is None
                or len(row) < 2
                or row[0] is None
                or row[1] is None
            ):
                continue

            role = str(row[0])
            created_at_raw = str(row[1])

            try:
                dt = datetime.fromisoformat(created_at_raw)
            except (ValueError, TypeError):
                continue

            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)

            if not (start_dt <= dt < end_exclusive_dt):
                continue

            total += 1
            if role == "user":
                user += 1
            elif role == "assistant":
                assistant += 1
            else:
                other += 1

            for idx, (b_start, b_end) in enumerate(bucket_intervals):
                if b_start <= dt < b_end:
                    buckets[idx]["message_count"] += 1
                    break

        return {
            "scope": "conversation activity",
            "day": day_str,
            "day_basis": "server-local calendar day",
            "start": start_iso,
            "end_exclusive": end_exclusive_iso,
            "bucket_hours": 4,
            "messages": {
                "total": total,
                "user": user,
                "assistant": assistant,
                "other": other,
            },
            "buckets": buckets,
        }
    except DashboardMetricsError:
        raise
    except Exception as error:
        raise DashboardMetricsError(
            "Dashboard activity is unavailable."
        ) from error
    finally:
        if connection is not None:
            _safe_close(connection)
