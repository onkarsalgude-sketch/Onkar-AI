"""Backend-aware conversational memory persistence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from app.config.settings import MEMORY_DB
from app.database.db import (
    get_connection,
    get_runtime_connection,
)
from app.database.memory_schema import (
    MEMORY_TABLE_NAME,
    MemorySchemaError,
    initialize_memory_schema,
)


class MemoryPersistenceError(
    RuntimeError
):
    """Raised without leaking database or message details."""

    def __init__(self):
        super().__init__(
            "Memory persistence operation failed."
        )


def _environment(
    environ: Mapping[str, str] | None,
) -> dict[str, str]:
    if environ is None:
        return dict(
            os.environ
        )

    return {
        str(key): str(value)
        for key, value
        in environ.items()
    }


def _uses_postgresql(
    environ: Mapping[str, str] | None,
) -> bool:
    environment = _environment(
        environ
    )

    database_url = str(
        environment.get(
            "DATABASE_URL",
            "",
        )
    ).strip().casefold()

    return database_url.startswith(
        (
            "postgres://",
            "postgresql://",
            "postgresql+psycopg://",
        )
    )


def _connect(
    environ: Mapping[str, str] | None,
):
    environment = _environment(
        environ
    )

    if _uses_postgresql(
        environment
    ):
        return (
            get_runtime_connection(
                environ=environment
            ),
            True,
        )

    return (
        get_connection(
            MEMORY_DB
        ),
        False,
    )


def _table_name(
    is_postgresql: bool,
) -> str:
    if is_postgresql:
        return (
            f"public."
            f"{MEMORY_TABLE_NAME}"
        )

    return MEMORY_TABLE_NAME


def _close_safely(
    resource,
) -> None:
    close = getattr(
        resource,
        "close",
        None,
    )

    if callable(close):
        close()


def _validated_limit(
    value: Any,
) -> int:
    try:
        limit = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise (
            MemoryPersistenceError()
        ) from error

    if limit <= 0 or limit > 1000:
        raise MemoryPersistenceError()

    return limit


def init_memory(
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    connection = None

    try:
        (
            connection,
            is_postgresql,
        ) = _connect(
            environ
        )

        initialize_memory_schema(
            connection,
            is_postgresql=(
                is_postgresql
            ),
        )

    except (
        MemorySchemaError,
        MemoryPersistenceError,
    ):
        raise

    except Exception as error:
        raise (
            MemoryPersistenceError()
        ) from error

    finally:
        if connection is not None:
            _close_safely(
                connection
            )


def add(
    role: str,
    content: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    resolved_role = str(
        role or ""
    ).strip()

    resolved_content = str(
        content or ""
    ).strip()

    if (
        not resolved_role
        or not resolved_content
        or len(resolved_role) > 100
    ):
        raise MemoryPersistenceError()

    connection = None
    cursor = None

    try:
        (
            connection,
            is_postgresql,
        ) = _connect(
            environ
        )

        initialize_memory_schema(
            connection,
            is_postgresql=(
                is_postgresql
            ),
        )

        cursor = connection.cursor()

        cursor.execute(
            f"""
            INSERT INTO
            {_table_name(is_postgresql)}
            (role, content)
            VALUES (?, ?)
            """,
            (
                resolved_role,
                resolved_content,
            ),
        )

        connection.commit()

    except (
        MemorySchemaError,
        MemoryPersistenceError,
    ):
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        raise

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        raise (
            MemoryPersistenceError()
        ) from error

    finally:
        if cursor is not None:
            _close_safely(
                cursor
            )

        if connection is not None:
            _close_safely(
                connection
            )


def get(
    limit: int = 10,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    resolved_limit = (
        _validated_limit(
            limit
        )
    )

    connection = None
    cursor = None

    try:
        (
            connection,
            is_postgresql,
        ) = _connect(
            environ
        )

        initialize_memory_schema(
            connection,
            is_postgresql=(
                is_postgresql
            ),
        )

        cursor = connection.cursor()

        cursor.execute(
            f"""
            SELECT role, content
            FROM {_table_name(is_postgresql)}
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                resolved_limit,
            ),
        )

        rows = cursor.fetchall()

        return [
            {
                "role": str(
                    row[0]
                ),
                "content": str(
                    row[1]
                ),
            }
            for row in reversed(
                rows
            )
        ]

    except (
        MemorySchemaError,
        MemoryPersistenceError,
    ):
        raise

    except Exception as error:
        raise (
            MemoryPersistenceError()
        ) from error

    finally:
        if cursor is not None:
            _close_safely(
                cursor
            )

        if connection is not None:
            _close_safely(
                connection
            )


def clear(
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    connection = None
    cursor = None

    try:
        (
            connection,
            is_postgresql,
        ) = _connect(
            environ
        )

        initialize_memory_schema(
            connection,
            is_postgresql=(
                is_postgresql
            ),
        )

        cursor = connection.cursor()

        cursor.execute(
            f"""
            DELETE FROM
            {_table_name(is_postgresql)}
            """
        )

        connection.commit()

    except (
        MemorySchemaError,
        MemoryPersistenceError,
    ):
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        raise

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass

        raise (
            MemoryPersistenceError()
        ) from error

    finally:
        if cursor is not None:
            _close_safely(
                cursor
            )

        if connection is not None:
            _close_safely(
                connection
            )
