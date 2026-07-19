"""Database backend configuration for SQLite and PostgreSQL.

This module only parses and validates configuration. It does not create
connections, initialize schemas, or migrate data.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class DatabaseConfigurationError(RuntimeError):
    """Fail-closed database configuration error."""

    def __init__(self):
        super().__init__("Database configuration is invalid.")


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    database_url: str | None
    sqlite_path: Path
    require_persistence: bool
    pool_size: int
    connect_timeout_seconds: int

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgresql(self) -> bool:
        return self.backend == "postgresql"

    @property
    def safe_target(self) -> str:
        """Return a credential-free target suitable for logs."""
        if self.is_sqlite:
            return f"sqlite:///{self.sqlite_path}"

        parsed = urlsplit(self.database_url or "")
        hostname = parsed.hostname or "unknown"

        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"

        port = f":{parsed.port}" if parsed.port is not None else ""
        database_name = parsed.path.lstrip("/") or "unknown"

        return f"postgresql://{hostname}{port}/{database_name}"


def _parse_bool(value) -> bool:
    normalized = str(value).strip().casefold()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"", "0", "false", "no", "off"}:
        return False

    raise DatabaseConfigurationError()


def _parse_positive_int(value) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise DatabaseConfigurationError() from error

    if parsed <= 0:
        raise DatabaseConfigurationError()

    return parsed


def _normalize_postgresql_url(value: str) -> str:
    candidate = str(value).strip()

    if (
        not candidate
        or any(character.isspace() for character in candidate)
    ):
        raise DatabaseConfigurationError()

    normalized_candidate = candidate.casefold()

    if normalized_candidate.startswith("postgres://"):
        candidate = (
            "postgresql+psycopg://"
            + candidate[len("postgres://"):]
        )
    elif normalized_candidate.startswith("postgresql://"):
        candidate = (
            "postgresql+psycopg://"
            + candidate[len("postgresql://"):]
        )

    try:
        parsed = urlsplit(candidate)
        parsed_port = parsed.port
    except ValueError as error:
        raise DatabaseConfigurationError() from error

    if (
        parsed.scheme not in {"postgresql", "postgresql+psycopg"}
        or parsed.hostname is None
        or not parsed.netloc
        or parsed.path in {"", "/"}
        or parsed.fragment
    ):
        raise DatabaseConfigurationError()

    if parsed_port is not None and not (1 <= parsed_port <= 65535):
        raise DatabaseConfigurationError()

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.query,
            "",
        )
    )


def load_database_settings(
    environ=None,
    *,
    default_sqlite_path: str | Path | None = None,
) -> DatabaseSettings:
    """Parse database settings without opening a connection."""
    source = os.environ if environ is None else environ

    fallback_path = (
        Path(default_sqlite_path)
        if default_sqlite_path is not None
        else Path(__file__).resolve().parents[1]
        / "database"
        / "chat_history.db"
    )

    raw_sqlite_path = str(
        source.get("SQLITE_DB_PATH", "")
    ).strip()

    sqlite_path = (
        Path(raw_sqlite_path).expanduser()
        if raw_sqlite_path
        else fallback_path
    )

    raw_database_url = str(
        source.get("DATABASE_URL", "")
    ).strip()

    require_persistence = _parse_bool(
        source.get("DATABASE_REQUIRE_PERSISTENCE", "false")
    )

    pool_size = _parse_positive_int(
        source.get("DATABASE_POOL_SIZE", "5")
    )

    connect_timeout_seconds = _parse_positive_int(
        source.get("DATABASE_CONNECT_TIMEOUT", "10")
    )

    if raw_database_url:
        database_url = _normalize_postgresql_url(
            raw_database_url
        )
        backend = "postgresql"
    else:
        database_url = None
        backend = "sqlite"

    if require_persistence and backend != "postgresql":
        raise DatabaseConfigurationError()

    return DatabaseSettings(
        backend=backend,
        database_url=database_url,
        sqlite_path=sqlite_path,
        require_persistence=require_persistence,
        pool_size=pool_size,
        connect_timeout_seconds=connect_timeout_seconds,
    )
