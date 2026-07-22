from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.config.system_incident_alerting import (
    SystemIncidentAlertingSettings,
    validate_system_incident_alerting_settings,
)
from app.database.db import (
    begin_write_transaction,
    get_runtime_connection,
)
from app.services.system_incident_alert_service import (
    build_system_incident_alert_payload,
)


DEFAULT_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS = 5
MIN_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS = 1
MAX_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS = 10

MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES = 32768
MAX_SYSTEM_INCIDENT_ALERT_DELIVERY_ID_LENGTH = 128


class SystemIncidentAlertOutboxError(RuntimeError):
    """Raised when a durable alert cannot be queued safely."""


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


def _normalize_max_attempts(
    value: Any,
) -> int:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            int,
        )
        or not (
            MIN_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS
            <= value
            <= MAX_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS
        )
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox max attempts are invalid."
        )

    return value


def _normalize_delivery_id(
    value: Any,
) -> str:
    normalized = str(
        value
    ).strip()

    if not (
        1
        <= len(
            normalized
        )
        <= MAX_SYSTEM_INCIDENT_ALERT_DELIVERY_ID_LENGTH
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox delivery ID is invalid."
        )

    return normalized


def _resolve_now(
    now: Callable[
        [],
        datetime,
    ] | None,
) -> datetime:
    now_fn = (
        now
        if now is not None
        else lambda: datetime.now(
            timezone.utc
        )
    )

    if not callable(
        now_fn
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox clock is invalid."
        )

    value = now_fn()

    if not isinstance(
        value,
        datetime,
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox clock is invalid."
        )

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _serialize_payload(
    payload: dict[str, Any],
) -> str:
    if not isinstance(
        payload,
        dict,
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox payload is invalid."
        )

    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(
                ",",
                ":",
            ),
            sort_keys=True,
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox payload is invalid."
        ) from error

    encoded_size = len(
        serialized.encode(
            "utf-8"
        )
    )

    if not (
        2
        <= len(
            serialized
        )
        <= MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES
        and encoded_size
        <= MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox payload is invalid."
        )

    return serialized


def enqueue_system_incident_alert(
    settings: SystemIncidentAlertingSettings,
    evaluation: dict[str, Any],
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    delivery_id_factory: Callable[
        [],
        Any,
    ] = uuid4,
    now: Callable[
        [],
        datetime,
    ] | None = None,
    max_attempts: int = (
        DEFAULT_SYSTEM_INCIDENT_ALERT_MAX_ATTEMPTS
    ),
) -> dict[str, Any]:
    """Queue one sanitized alert payload in the durable outbox."""
    validate_system_incident_alerting_settings(
        settings
    )

    if not settings.enabled:
        return {
            "service": (
                "system_incident_alert_outbox"
            ),
            "queued": False,
            "reason": "disabled",
            "delivery_id": None,
            "transition_count": 0,
        }

    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox connection factory is invalid."
        )

    if not callable(
        delivery_id_factory
    ):
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox delivery ID factory is invalid."
        )

    normalized_max_attempts = (
        _normalize_max_attempts(
            max_attempts
        )
    )

    resolved_now = _resolve_now(
        now
    )

    try:
        payload = (
            build_system_incident_alert_payload(
                evaluation,
                now=lambda: resolved_now,
            )
        )
    except Exception as error:
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox payload could not be built."
        ) from error

    if payload is None:
        return {
            "service": (
                "system_incident_alert_outbox"
            ),
            "queued": False,
            "reason": "no_transitions",
            "delivery_id": None,
            "transition_count": 0,
        }

    payload_json = _serialize_payload(
        payload
    )

    try:
        delivery_id = _normalize_delivery_id(
            delivery_id_factory()
        )
    except SystemIncidentAlertOutboxError:
        raise
    except Exception as error:
        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox delivery ID could not be created."
        ) from error

    timestamp = resolved_now.isoformat()

    connection = None

    try:
        connection = connection_factory(
            db_path
        )

        cursor = connection.cursor()

        begin_write_transaction(
            connection
        )

        cursor.execute(
            """
            INSERT INTO system_incident_alert_outbox (
                delivery_id,
                payload_json,
                state,
                attempt_count,
                max_attempts,
                next_attempt_at,
                claimed_at,
                claim_token,
                created_at,
                updated_at,
                completed_at
            )
            VALUES (
                ?, ?,
                'pending',
                0, ?,
                ?,
                NULL,
                NULL,
                ?,
                ?,
                NULL
            )
            """,
            (
                delivery_id,
                payload_json,
                normalized_max_attempts,
                timestamp,
                timestamp,
                timestamp,
            ),
        )

        if (
            cursor.rowcount is not None
            and int(
                cursor.rowcount
            )
            not in (
                -1,
                1,
            )
        ):
            raise SystemIncidentAlertOutboxError(
                "System incident alert outbox insert failed."
            )

        connection.commit()

        return {
            "service": (
                "system_incident_alert_outbox"
            ),
            "queued": True,
            "reason": "queued",
            "delivery_id": delivery_id,
            "state": "pending",
            "attempt_count": 0,
            "max_attempts": (
                normalized_max_attempts
            ),
            "next_attempt_at": timestamp,
            "transition_count": int(
                payload.get(
                    "transition_count",
                    0,
                )
            ),
        }
    except SystemIncidentAlertOutboxError:
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

        raise SystemIncidentAlertOutboxError(
            "System incident alert outbox write failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )
