"""Database connection helpers.

Legacy SQLite services continue using get_connection().
Migrated services use get_runtime_connection(), which supports SQLite
locally and PostgreSQL through Psycopg in production.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from threading import Lock
from typing import Any

from sqlalchemy.engine import Engine

from app.config.database import (
    DatabaseSettings,
    load_database_settings,
)
from app.database.engine import build_database_engine


_ENGINE_CACHE: dict[
    tuple[str, int, int],
    Engine,
] = {}

_ENGINE_CACHE_LOCK = Lock()


def get_connection(db_path: str):
    """Return the original SQLite connection for legacy services."""
    return sqlite3.connect(db_path)


def _convert_qmark_placeholders(
    sql: str,
) -> str:
    """Convert SQLite qmark binds to Psycopg %s binds safely."""
    result: list[str] = []
    index = 0
    state = "normal"

    while index < len(sql):
        character = sql[index]
        next_character = (
            sql[index + 1]
            if index + 1 < len(sql)
            else ""
        )

        if state == "normal":
            if (
                character == "-"
                and next_character == "-"
            ):
                result.extend(
                    (
                        character,
                        next_character,
                    )
                )
                index += 2
                state = "line_comment"
                continue

            if (
                character == "/"
                and next_character == "*"
            ):
                result.extend(
                    (
                        character,
                        next_character,
                    )
                )
                index += 2
                state = "block_comment"
                continue

            if character == "'":
                result.append(character)
                index += 1
                state = "single_quote"
                continue

            if character == '"':
                result.append(character)
                index += 1
                state = "double_quote"
                continue

            if character == "?":
                result.append("%s")
                index += 1
                continue

            result.append(character)
            index += 1
            continue

        if state == "single_quote":
            result.append(character)

            if (
                character == "'"
                and next_character == "'"
            ):
                result.append(next_character)
                index += 2
                continue

            if character == "'":
                state = "normal"

            index += 1
            continue

        if state == "double_quote":
            result.append(character)

            if (
                character == '"'
                and next_character == '"'
            ):
                result.append(next_character)
                index += 2
                continue

            if character == '"':
                state = "normal"

            index += 1
            continue

        if state == "line_comment":
            result.append(character)
            index += 1

            if character == "\n":
                state = "normal"

            continue

        if state == "block_comment":
            result.append(character)

            if (
                character == "*"
                and next_character == "/"
            ):
                result.append(next_character)
                index += 2
                state = "normal"
                continue

            index += 1

    return "".join(result)


class PortableRow(Sequence[Any]):
    """Tuple-like row supporting numeric and column-name access."""

    def __init__(
        self,
        values: Sequence[Any],
        column_names: Sequence[str],
    ):
        self._values = tuple(values)
        self._positions = {
            name: position
            for position, name in enumerate(
                column_names
            )
        }

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[
                self._positions[key]
            ]

        return self._values[key]

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def keys(self):
        return self._positions.keys()

    def __repr__(self) -> str:
        return repr(self._values)


class PortableCursor:
    """Small DB-API compatibility wrapper for Psycopg cursors."""

    def __init__(
        self,
        raw_cursor,
        owner: "PortableConnection",
    ):
        self._raw_cursor = raw_cursor
        self._owner = owner

    def execute(
        self,
        sql: str,
        parameters: Any = None,
    ):
        portable_sql = (
            _convert_qmark_placeholders(sql)
        )

        if parameters is None:
            self._raw_cursor.execute(
                portable_sql
            )
        else:
            self._raw_cursor.execute(
                portable_sql,
                parameters,
            )

        return self

    def executemany(
        self,
        sql: str,
        parameter_sets,
    ):
        self._raw_cursor.executemany(
            _convert_qmark_placeholders(sql),
            parameter_sets,
        )

        return self

    def _column_names(self) -> tuple[str, ...]:
        description = (
            self._raw_cursor.description
            or ()
        )

        names = []

        for column in description:
            name = getattr(
                column,
                "name",
                None,
            )

            if name is None:
                name = column[0]

            names.append(str(name))

        return tuple(names)

    def _wrap_row(self, row):
        if (
            row is None
            or self._owner.row_factory
            is None
        ):
            return row

        return PortableRow(
            row,
            self._column_names(),
        )

    def fetchone(self):
        return self._wrap_row(
            self._raw_cursor.fetchone()
        )

    def fetchmany(self, size=None):
        if size is None:
            rows = self._raw_cursor.fetchmany()
        else:
            rows = self._raw_cursor.fetchmany(
                size
            )

        return [
            self._wrap_row(row)
            for row in rows
        ]

    def fetchall(self):
        return [
            self._wrap_row(row)
            for row in (
                self._raw_cursor.fetchall()
            )
        ]

    def close(self):
        return self._raw_cursor.close()

    @property
    def description(self):
        return self._raw_cursor.description

    @property
    def rowcount(self):
        return self._raw_cursor.rowcount

    @property
    def lastrowid(self):
        return getattr(
            self._raw_cursor,
            "lastrowid",
            None,
        )

    def __iter__(self):
        for row in self._raw_cursor:
            yield self._wrap_row(row)


class PortableConnection:
    """Connection wrapper preserving the APIs used by existing services."""

    def __init__(self, raw_connection):
        self._raw_connection = raw_connection
        self.row_factory = None

    def cursor(self) -> PortableCursor:
        return PortableCursor(
            self._raw_connection.cursor(),
            self,
        )

    def execute(
        self,
        sql: str,
        parameters: Any = None,
    ) -> PortableCursor:
        cursor = self.cursor()
        cursor.execute(sql, parameters)
        return cursor

    def commit(self):
        return self._raw_connection.commit()

    def rollback(self):
        return self._raw_connection.rollback()

    def close(self):
        return self._raw_connection.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exception_type,
        exception,
        traceback,
    ):
        try:
            if exception_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()

        return False


def _get_runtime_engine(
    settings: DatabaseSettings,
) -> Engine:
    key = (
        settings.database_url,
        settings.pool_size,
        settings.connect_timeout_seconds,
    )

    with _ENGINE_CACHE_LOCK:
        engine = _ENGINE_CACHE.get(key)

        if engine is None:
            engine = build_database_engine(
                settings
            )
            _ENGINE_CACHE[key] = engine

        return engine


def close_runtime_engines() -> None:
    """Dispose cached PostgreSQL pools, mainly for tests and shutdown."""
    with _ENGINE_CACHE_LOCK:
        engines = tuple(
            _ENGINE_CACHE.values()
        )
        _ENGINE_CACHE.clear()

    for engine in engines:
        engine.dispose()


def get_runtime_connection(
    db_path: str | None = None,
    *,
    environ: Mapping[str, str]
    | None = None,
):
    """Return SQLite locally or a portable Psycopg connection in production."""
    settings = load_database_settings(
        environ,
        default_sqlite_path=db_path,
    )

    if settings.is_sqlite:
        return sqlite3.connect(
            str(settings.sqlite_path)
        )

    engine = _get_runtime_engine(
        settings
    )

    return PortableConnection(
        engine.raw_connection()
    )
