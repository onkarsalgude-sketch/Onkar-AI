"""Instance Profile service providing durable local profile configuration."""

from datetime import datetime, timezone
from pathlib import Path
import re
import zoneinfo

from app.config.settings import CHAT_DB
from app.database.db import get_runtime_connection


class ProfileValidationError(ValueError):
    """Raised when profile payload fails semantic validation."""

    pass


class ProfilePersistenceError(RuntimeError):
    """Raised when profile database operations fail."""

    pass


_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def derive_avatar_initials(display_name: str | None) -> str | None:
    """Derive 1-2 uppercase avatar initials from display name."""
    if not display_name or not isinstance(display_name, str):
        return None

    trimmed = display_name.strip()
    if not trimmed:
        return None

    words = trimmed.split()
    if len(words) >= 2:
        first = words[0][0]
        last = words[-1][0]
        return (first + last).upper()

    single_word = words[0]
    return single_word[:2].upper()


def _validate_display_name(display_name: str | None) -> str:
    if display_name is None or not isinstance(display_name, str):
        raise ProfileValidationError("Display name must be a valid non-empty string.")

    trimmed = display_name.strip()
    if not trimmed:
        raise ProfileValidationError("Display name cannot be empty or whitespace only.")

    if len(trimmed) > 50:
        raise ProfileValidationError("Display name must not exceed 50 characters.")

    if _CONTROL_CHAR_PATTERN.search(trimmed):
        raise ProfileValidationError("Display name contains invalid control characters.")

    return trimmed


def _validate_timezone(tz_value: str | None) -> str | None:
    if tz_value is None:
        return None

    if not isinstance(tz_value, str):
        raise ProfileValidationError("Timezone must be a string or null.")

    trimmed = tz_value.strip()
    if not trimmed:
        raise ProfileValidationError("Timezone string cannot be blank.")

    try:
        zoneinfo.ZoneInfo(trimmed)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ProfileValidationError("Invalid IANA timezone string.") from error

    return trimmed


def _default_now_provider() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_db_path(db_path: str | Path | None) -> str:
    if db_path is not None:
        return str(db_path)
    return str(CHAT_DB)


def get_instance_profile(
    *,
    db_path: str | Path | None = None,
    connection_factory=get_runtime_connection,
) -> dict:
    """Retrieve the current instance profile or unconfigured default."""
    resolved_path = _resolve_db_path(db_path)
    connection = None
    cursor = None

    try:
        connection = connection_factory(resolved_path)
        cursor = connection.cursor()

        cursor.execute(
            "SELECT display_name, timezone, created_at, updated_at FROM instance_profile WHERE id = 1"
        )
        row = cursor.fetchone()

        if not row:
            return {
                "configured": False,
                "display_name": None,
                "avatar_initials": None,
                "timezone": None,
                "created_at": None,
                "updated_at": None,
            }

        display_name, tz_str, created_at, updated_at = row[0], row[1], row[2], row[3]

        return {
            "configured": True,
            "display_name": display_name,
            "avatar_initials": derive_avatar_initials(display_name),
            "timezone": tz_str,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    except ProfileValidationError:
        raise
    except Exception as error:
        raise ProfilePersistenceError("Profile storage failed.") from error
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None and hasattr(connection, "close"):
            try:
                connection.close()
            except Exception:
                pass


def update_instance_profile(
    *,
    display_name: str | None,
    timezone: str | None = None,
    db_path: str | Path | None = None,
    connection_factory=get_runtime_connection,
    now_provider=_default_now_provider,
) -> dict:
    """Create or update the singleton instance profile."""
    clean_display_name = _validate_display_name(display_name)
    clean_timezone = _validate_timezone(timezone)

    now_dt = now_provider()
    if not isinstance(now_dt, datetime):
        now_dt = datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    now_iso = now_dt.isoformat()
    resolved_path = _resolve_db_path(db_path)
    connection = None
    cursor = None

    try:
        connection = connection_factory(resolved_path)
        cursor = connection.cursor()

        cursor.execute("SELECT id, created_at FROM instance_profile WHERE id = 1")
        row = cursor.fetchone()

        if row:
            cursor.execute(
                "UPDATE instance_profile SET display_name = ?, timezone = ?, updated_at = ? WHERE id = 1",
                (clean_display_name, clean_timezone, now_iso),
            )
        else:
            cursor.execute(
                "INSERT INTO instance_profile (id, display_name, timezone, created_at, updated_at) VALUES (1, ?, ?, ?, ?)",
                (clean_display_name, clean_timezone, now_iso, now_iso),
            )

        if hasattr(connection, "commit"):
            connection.commit()

        return get_instance_profile(
            db_path=resolved_path,
            connection_factory=connection_factory,
        )

    except ProfileValidationError:
        raise
    except Exception as error:
        if connection is not None and hasattr(connection, "rollback"):
            try:
                connection.rollback()
            except Exception:
                pass
        raise ProfilePersistenceError("Profile storage failed.") from error
    finally:
        if cursor is not None and hasattr(cursor, "close"):
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None and hasattr(connection, "close"):
            try:
                connection.close()
            except Exception:
                pass
