"""Read-only aggregate metrics for the admin dashboard."""

from __future__ import annotations

from typing import Any, Callable

from app.config.settings import CHAT_DB
from app.database.db import get_runtime_connection
from app.services.document_recovery_history_service import (
    MAX_HISTORY_LIMIT as RECOVERY_HISTORY_LIMIT,
    summarize_document_recovery_runs,
)
from app.services.system_incident_history_service import (
    MAX_HISTORY_LIMIT as INCIDENT_HISTORY_LIMIT,
    summarize_system_incidents,
)


DB_PATH = str(CHAT_DB)
MAX_AGENT_USAGE_ROWS = 25


class DashboardMetricsError(RuntimeError):
    """Raised when core dashboard usage metrics cannot be read safely."""


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
