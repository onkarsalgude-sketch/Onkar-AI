from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
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
from app.services.system_incident_alert_outbox_service import (
    MAX_SYSTEM_INCIDENT_ALERT_DELIVERY_ID_LENGTH,
    MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES,
)
from app.services.system_incident_alert_service import (
    _send_https_json,
)


DEFAULT_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS = 30.0
MAX_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS = 3600.0
MAX_SYSTEM_INCIDENT_ALERT_STALE_SECONDS = 86400.0
MIN_SYSTEM_INCIDENT_ALERT_STALE_SECONDS = 1.0
MAX_SYSTEM_INCIDENT_ALERT_CLAIM_TOKEN_LENGTH = 128


class SystemIncidentAlertOutboxWorkerError(
    RuntimeError
):
    """Raised when durable alert delivery cannot advance safely."""


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
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox worker clock is invalid."
        )

    value = now_fn()

    if not isinstance(
        value,
        datetime,
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox worker clock is invalid."
        )

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _normalize_claim_token(
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
        <= MAX_SYSTEM_INCIDENT_ALERT_CLAIM_TOKEN_LENGTH
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox claim token is invalid."
        )

    return normalized


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
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox delivery ID is invalid."
        )

    return normalized


def _normalize_jitter_value(
    value: Any,
) -> float:
    if isinstance(
        value,
        bool,
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox jitter is invalid."
        )

    try:
        normalized = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox jitter is invalid."
        ) from error

    if not (
        0.0
        <= normalized
        <= 1.0
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox jitter is invalid."
        )

    return normalized


def _resolve_jitter(
    jitter: Callable[
        [],
        float,
    ] | None,
) -> float:
    jitter_fn = (
        jitter
        if jitter is not None
        else random.random
    )

    if not callable(
        jitter_fn
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox jitter source is invalid."
        )

    return _normalize_jitter_value(
        jitter_fn()
    )


def _normalize_stale_after_seconds(
    value: Any,
) -> float:
    if isinstance(
        value,
        bool,
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert stale interval is invalid."
        )

    try:
        normalized = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert stale interval is invalid."
        ) from error

    if not (
        MIN_SYSTEM_INCIDENT_ALERT_STALE_SECONDS
        <= normalized
        <= MAX_SYSTEM_INCIDENT_ALERT_STALE_SECONDS
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert stale interval is invalid."
        )

    return normalized


def compute_system_incident_alert_backoff_seconds(
    attempt_count: int,
    *,
    jitter_value: float,
    base_seconds: float = (
        DEFAULT_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
    maximum_seconds: float = (
        MAX_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
) -> float:
    """Return bounded exponential backoff with proportional jitter."""
    if (
        isinstance(
            attempt_count,
            bool,
        )
        or not isinstance(
            attempt_count,
            int,
        )
        or attempt_count < 1
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert attempt count is invalid."
        )

    normalized_jitter = (
        _normalize_jitter_value(
            jitter_value
        )
    )

    try:
        normalized_base = float(
            base_seconds
        )
        normalized_maximum = float(
            maximum_seconds
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert backoff configuration is invalid."
        ) from error

    if (
        normalized_base <= 0
        or normalized_maximum
        < normalized_base
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert backoff configuration is invalid."
        )

    exponent = min(
        attempt_count - 1,
        20,
    )

    deterministic = min(
        normalized_maximum,
        normalized_base
        * (
            2 ** exponent
        ),
    )

    jittered = deterministic * (
        1.0
        + (
            0.25
            * normalized_jitter
        )
    )

    return min(
        normalized_maximum,
        jittered,
    )


def _row_mapping(
    cursor: Any,
    row: Any,
) -> dict[str, Any]:
    description = getattr(
        cursor,
        "description",
        None,
    )

    if (
        not description
        or row is None
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox row is invalid."
        )

    names = [
        str(
            item[0]
        )
        for item in description
    ]

    values = tuple(
        row
    )

    if len(
        names
    ) != len(
        values
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox row is invalid."
        )

    return dict(
        zip(
            names,
            values,
        )
    )


def _deserialize_payload(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        str,
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox payload is invalid."
        )

    encoded_size = len(
        value.encode(
            "utf-8"
        )
    )

    if not (
        2
        <= len(
            value
        )
        <= MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES
        and encoded_size
        <= MAX_SYSTEM_INCIDENT_ALERT_OUTBOX_PAYLOAD_BYTES
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox payload is invalid."
        )

    try:
        payload = json.loads(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox payload is invalid."
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox payload is invalid."
        )

    transitions = payload.get(
        "transitions"
    )
    transition_count = payload.get(
        "transition_count"
    )

    if (
        payload.get(
            "service"
        )
        != "system_incidents"
        or payload.get(
            "event"
        )
        != "incident_transitions"
        or not isinstance(
            transitions,
            list,
        )
        or isinstance(
            transition_count,
            bool,
        )
        or not isinstance(
            transition_count,
            int,
        )
        or transition_count < 1
        or transition_count
        != len(
            transitions
        )
        or not all(
            isinstance(
                item,
                dict,
            )
            for item in transitions
        )
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox payload is invalid."
        )

    return payload


def claim_due_system_incident_alert(
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    claim_token_factory: Callable[
        [],
        Any,
    ] = uuid4,
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> dict[str, Any] | None:
    """Atomically claim one due pending alert for delivery."""
    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox connection factory is invalid."
        )

    if not callable(
        claim_token_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert claim token factory is invalid."
        )

    resolved_now = _resolve_now(
        now
    )

    try:
        claim_token = _normalize_claim_token(
            claim_token_factory()
        )
    except SystemIncidentAlertOutboxWorkerError:
        raise
    except Exception as error:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert claim token could not be created."
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
            SELECT
                delivery_id,
                payload_json,
                attempt_count,
                max_attempts,
                next_attempt_at
            FROM system_incident_alert_outbox
            WHERE
                state = 'pending'
                AND next_attempt_at <= ?
                AND attempt_count < max_attempts
            ORDER BY
                next_attempt_at ASC,
                delivery_id ASC
            LIMIT 1
            """,
            (
                timestamp,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            connection.commit()
            return None

        record = _row_mapping(
            cursor,
            row,
        )

        delivery_id = _normalize_delivery_id(
            record.get(
                "delivery_id"
            )
        )

        current_attempt_count = int(
            record.get(
                "attempt_count"
            )
        )
        max_attempts = int(
            record.get(
                "max_attempts"
            )
        )

        if not (
            0
            <= current_attempt_count
            < max_attempts
            <= 10
        ):
            raise SystemIncidentAlertOutboxWorkerError(
                "System incident alert outbox attempt state is invalid."
            )

        cursor.execute(
            """
            UPDATE system_incident_alert_outbox
            SET
                state = 'processing',
                attempt_count = attempt_count + 1,
                claimed_at = ?,
                claim_token = ?,
                updated_at = ?
            WHERE
                delivery_id = ?
                AND state = 'pending'
                AND next_attempt_at <= ?
                AND attempt_count = ?
                AND attempt_count < max_attempts
            """,
            (
                timestamp,
                claim_token,
                timestamp,
                delivery_id,
                timestamp,
                current_attempt_count,
            ),
        )

        if int(
            cursor.rowcount
        ) != 1:
            connection.commit()
            return None

        connection.commit()

        return {
            "delivery_id": delivery_id,
            "payload_json": str(
                record.get(
                    "payload_json"
                )
            ),
            "attempt_count": (
                current_attempt_count
                + 1
            ),
            "max_attempts": max_attempts,
            "claimed_at": timestamp,
            "claim_token": claim_token,
        }
    except SystemIncidentAlertOutboxWorkerError:
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

        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox claim failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def complete_claimed_system_incident_alert(
    delivery_id: Any,
    claim_token: Any,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> bool:
    """Idempotently complete one alert owned by the supplied claim token."""
    normalized_delivery_id = (
        _normalize_delivery_id(
            delivery_id
        )
    )
    normalized_claim_token = (
        _normalize_claim_token(
            claim_token
        )
    )

    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox connection factory is invalid."
        )

    timestamp = _resolve_now(
        now
    ).isoformat()

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
            UPDATE system_incident_alert_outbox
            SET
                state = 'completed',
                updated_at = ?,
                completed_at = ?
            WHERE
                delivery_id = ?
                AND state = 'processing'
                AND claim_token = ?
            """,
            (
                timestamp,
                timestamp,
                normalized_delivery_id,
                normalized_claim_token,
            ),
        )

        updated = int(
            cursor.rowcount
        ) == 1

        connection.commit()

        return updated
    except SystemIncidentAlertOutboxWorkerError:
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

        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert completion failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def fail_claimed_system_incident_alert(
    delivery_id: Any,
    claim_token: Any,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> bool:
    """Idempotently terminalize one claimed alert without storing error text."""
    normalized_delivery_id = (
        _normalize_delivery_id(
            delivery_id
        )
    )
    normalized_claim_token = (
        _normalize_claim_token(
            claim_token
        )
    )

    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox connection factory is invalid."
        )

    timestamp = _resolve_now(
        now
    ).isoformat()

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
            UPDATE system_incident_alert_outbox
            SET
                state = 'failed',
                updated_at = ?,
                completed_at = ?
            WHERE
                delivery_id = ?
                AND state = 'processing'
                AND claim_token = ?
            """,
            (
                timestamp,
                timestamp,
                normalized_delivery_id,
                normalized_claim_token,
            ),
        )

        updated = int(
            cursor.rowcount
        ) == 1

        connection.commit()

        return updated
    except SystemIncidentAlertOutboxWorkerError:
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

        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert failure update failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def retry_or_fail_claimed_system_incident_alert(
    delivery_id: Any,
    claim_token: Any,
    *,
    attempt_count: int,
    max_attempts: int,
    jitter_value: float,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    now: Callable[
        [],
        datetime,
    ] | None = None,
    base_backoff_seconds: float = (
        DEFAULT_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
    maximum_backoff_seconds: float = (
        MAX_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
) -> dict[str, Any]:
    """Persist either a retry schedule or terminal failure for one claim."""
    normalized_delivery_id = (
        _normalize_delivery_id(
            delivery_id
        )
    )
    normalized_claim_token = (
        _normalize_claim_token(
            claim_token
        )
    )

    if (
        isinstance(
            attempt_count,
            bool,
        )
        or isinstance(
            max_attempts,
            bool,
        )
        or not isinstance(
            attempt_count,
            int,
        )
        or not isinstance(
            max_attempts,
            int,
        )
        or not (
            1
            <= attempt_count
            <= max_attempts
            <= 10
        )
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert retry state is invalid."
        )

    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox connection factory is invalid."
        )

    resolved_now = _resolve_now(
        now
    )
    timestamp = resolved_now.isoformat()

    terminal = (
        attempt_count
        >= max_attempts
    )

    next_attempt_at = None

    if not terminal:
        delay_seconds = (
            compute_system_incident_alert_backoff_seconds(
                attempt_count,
                jitter_value=jitter_value,
                base_seconds=(
                    base_backoff_seconds
                ),
                maximum_seconds=(
                    maximum_backoff_seconds
                ),
            )
        )

        next_attempt_at = (
            resolved_now
            + timedelta(
                seconds=delay_seconds
            )
        ).isoformat()

    connection = None

    try:
        connection = connection_factory(
            db_path
        )
        cursor = connection.cursor()

        begin_write_transaction(
            connection
        )

        if terminal:
            cursor.execute(
                """
                UPDATE system_incident_alert_outbox
                SET
                    state = 'failed',
                    updated_at = ?,
                    completed_at = ?
                WHERE
                    delivery_id = ?
                    AND state = 'processing'
                    AND claim_token = ?
                    AND attempt_count = ?
                    AND max_attempts = ?
                """,
                (
                    timestamp,
                    timestamp,
                    normalized_delivery_id,
                    normalized_claim_token,
                    attempt_count,
                    max_attempts,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE system_incident_alert_outbox
                SET
                    state = 'pending',
                    next_attempt_at = ?,
                    claimed_at = NULL,
                    claim_token = NULL,
                    updated_at = ?,
                    completed_at = NULL
                WHERE
                    delivery_id = ?
                    AND state = 'processing'
                    AND claim_token = ?
                    AND attempt_count = ?
                    AND max_attempts = ?
                """,
                (
                    next_attempt_at,
                    timestamp,
                    normalized_delivery_id,
                    normalized_claim_token,
                    attempt_count,
                    max_attempts,
                ),
            )

        updated = int(
            cursor.rowcount
        ) == 1

        connection.commit()

        return {
            "updated": updated,
            "state": (
                "failed"
                if terminal
                else "pending"
            ),
            "next_attempt_at": (
                next_attempt_at
            ),
        }
    except SystemIncidentAlertOutboxWorkerError:
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

        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert retry update failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def recover_stale_system_incident_alert_claims(
    *,
    stale_after_seconds: float,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    now: Callable[
        [],
        datetime,
    ] | None = None,
) -> dict[str, int]:
    """Recover stale processing claims without exposing stored payloads."""
    normalized_stale_seconds = (
        _normalize_stale_after_seconds(
            stale_after_seconds
        )
    )

    if not callable(
        connection_factory
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert outbox connection factory is invalid."
        )

    resolved_now = _resolve_now(
        now
    )
    timestamp = resolved_now.isoformat()
    stale_before = (
        resolved_now
        - timedelta(
            seconds=normalized_stale_seconds
        )
    ).isoformat()

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
            UPDATE system_incident_alert_outbox
            SET
                state = 'pending',
                next_attempt_at = ?,
                claimed_at = NULL,
                claim_token = NULL,
                updated_at = ?,
                completed_at = NULL
            WHERE
                state = 'processing'
                AND claimed_at <= ?
                AND attempt_count < max_attempts
            """,
            (
                timestamp,
                timestamp,
                stale_before,
            ),
        )

        recovered_count = max(
            0,
            int(
                cursor.rowcount
            ),
        )

        cursor.execute(
            """
            UPDATE system_incident_alert_outbox
            SET
                state = 'failed',
                updated_at = ?,
                completed_at = ?
            WHERE
                state = 'processing'
                AND claimed_at <= ?
                AND attempt_count >= max_attempts
            """,
            (
                timestamp,
                timestamp,
                stale_before,
            ),
        )

        failed_count = max(
            0,
            int(
                cursor.rowcount
            ),
        )

        connection.commit()

        return {
            "recovered_count": recovered_count,
            "failed_count": failed_count,
        }
    except SystemIncidentAlertOutboxWorkerError:
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

        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert stale-claim recovery failed."
        ) from error
    finally:
        if connection is not None:
            _safe_close(
                connection
            )


def process_next_system_incident_alert(
    settings: SystemIncidentAlertingSettings,
    *,
    db_path: str | None = None,
    connection_factory: Callable = (
        get_runtime_connection
    ),
    sender: Callable[
        [
            str,
            dict[str, Any],
            float,
        ],
        None,
    ] = _send_https_json,
    now: Callable[
        [],
        datetime,
    ] | None = None,
    jitter: Callable[
        [],
        float,
    ] | None = None,
    claim_token_factory: Callable[
        [],
        Any,
    ] = uuid4,
    base_backoff_seconds: float = (
        DEFAULT_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
    maximum_backoff_seconds: float = (
        MAX_SYSTEM_INCIDENT_ALERT_BACKOFF_SECONDS
    ),
) -> dict[str, Any]:
    """Claim and advance at most one durable alert delivery."""
    validate_system_incident_alerting_settings(
        settings
    )

    if not settings.enabled:
        return {
            "service": (
                "system_incident_alert_outbox_worker"
            ),
            "enabled": False,
            "attempted": False,
            "state": None,
            "delivery_id": None,
        }

    if not callable(
        sender
    ):
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert sender is invalid."
        )

    resolved_now = _resolve_now(
        now
    )
    jitter_value = _resolve_jitter(
        jitter
    )

    claim = claim_due_system_incident_alert(
        db_path=db_path,
        connection_factory=connection_factory,
        claim_token_factory=(
            claim_token_factory
        ),
        now=lambda: resolved_now,
    )

    if claim is None:
        return {
            "service": (
                "system_incident_alert_outbox_worker"
            ),
            "enabled": True,
            "attempted": False,
            "state": "idle",
            "delivery_id": None,
        }

    delivery_id = str(
        claim["delivery_id"]
    )
    claim_token = str(
        claim["claim_token"]
    )

    try:
        payload = _deserialize_payload(
            claim["payload_json"]
        )
    except SystemIncidentAlertOutboxWorkerError:
        updated = fail_claimed_system_incident_alert(
            delivery_id,
            claim_token,
            db_path=db_path,
            connection_factory=connection_factory,
            now=lambda: resolved_now,
        )

        if not updated:
            raise SystemIncidentAlertOutboxWorkerError(
                "System incident alert invalid-payload update failed."
            )

        return {
            "service": (
                "system_incident_alert_outbox_worker"
            ),
            "enabled": True,
            "attempted": False,
            "state": "failed",
            "delivery_id": delivery_id,
        }

    try:
        sender(
            settings.webhook_url,
            payload,
            settings.timeout_seconds,
        )
    except Exception:
        retry_result = (
            retry_or_fail_claimed_system_incident_alert(
                delivery_id,
                claim_token,
                attempt_count=int(
                    claim["attempt_count"]
                ),
                max_attempts=int(
                    claim["max_attempts"]
                ),
                jitter_value=jitter_value,
                db_path=db_path,
                connection_factory=(
                    connection_factory
                ),
                now=lambda: resolved_now,
                base_backoff_seconds=(
                    base_backoff_seconds
                ),
                maximum_backoff_seconds=(
                    maximum_backoff_seconds
                ),
            )
        )

        if not retry_result[
            "updated"
        ]:
            raise SystemIncidentAlertOutboxWorkerError(
                "System incident alert retry state update failed."
            )

        return {
            "service": (
                "system_incident_alert_outbox_worker"
            ),
            "enabled": True,
            "attempted": True,
            "state": retry_result[
                "state"
            ],
            "delivery_id": delivery_id,
            "next_attempt_at": retry_result[
                "next_attempt_at"
            ],
        }

    completed = (
        complete_claimed_system_incident_alert(
            delivery_id,
            claim_token,
            db_path=db_path,
            connection_factory=connection_factory,
            now=lambda: resolved_now,
        )
    )

    if not completed:
        raise SystemIncidentAlertOutboxWorkerError(
            "System incident alert completion state update failed."
        )

    return {
        "service": (
            "system_incident_alert_outbox_worker"
        ),
        "enabled": True,
        "attempted": True,
        "state": "completed",
        "delivery_id": delivery_id,
        "next_attempt_at": None,
    }
