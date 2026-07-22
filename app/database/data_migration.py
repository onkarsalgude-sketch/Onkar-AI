"""Explicit SQLite-to-PostgreSQL data migration support."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from sqlalchemy import (
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine, URL
from sqlalchemy.pool import NullPool

from app.database.migrations import (
    SchemaCompatibilityError,
    initialize_schema,
    validate_existing_schema,
)
from app.database.schema import (
    branch_merge_message_mappings,
    branch_merge_operations,
    chats,
    documents,
    document_recovery_runs,
    folders,
    message_bookmarks,
    messages,
    system_incidents,
)


class DataMigrationError(RuntimeError):
    """Raised when data cannot be migrated safely."""


_APPLICATION_TABLES = (
    folders,
    chats,
    messages,
    message_bookmarks,
    documents,
    branch_merge_operations,
    branch_merge_message_mappings,
    document_recovery_runs,
    system_incidents,
)

_OPTIONAL_SOURCE_TABLE_NAMES = frozenset(
    {
        document_recovery_runs.name,
        system_incidents.name,
    }
)


_TABLE_BY_NAME = {
    table.name: table
    for table in _APPLICATION_TABLES
}

_INSERT_ORDER = (
    folders,
    chats,
    messages,
    message_bookmarks,
    documents,
    branch_merge_operations,
    branch_merge_message_mappings,
    document_recovery_runs,
    system_incidents,
)

_CHAT_RELATION_COLUMNS = (
    "parent_chat_id",
    "branched_from_message_id",
    "branch_message_id",
)

_SEQUENCE_TABLES = (
    folders,
    chats,
    messages,
    message_bookmarks,
    branch_merge_operations,
    branch_merge_message_mappings,
)


@dataclass(frozen=True)
class MigrationReport:
    source_path: Path
    target_backend: str
    row_counts: MappingProxyType

    @property
    def total_rows(self) -> int:
        return sum(
            self.row_counts.values()
        )


def _quote_sqlite_identifier(
    value: str,
) -> str:
    return (
        '"'
        + str(value).replace('"', '""')
        + '"'
    )


def _build_source_engine(
    source_path: Path,
) -> Engine:
    return create_engine(
        URL.create(
            "sqlite",
            database=str(source_path),
        ),
        connect_args={
            "check_same_thread": False,
        },
        poolclass=NullPool,
        future=True,
    )


def _read_source_rows(
    connection: sqlite3.Connection,
    table,
) -> list[dict]:
    column_names = list(
        table.c.keys()
    )

    quoted_columns = ", ".join(
        _quote_sqlite_identifier(
            column_name
        )
        for column_name in column_names
    )

    sql = (
        f"SELECT {quoted_columns} "
        f"FROM "
        f"{_quote_sqlite_identifier(table.name)}"
    )

    primary_key_names = [
        column.name
        for column in table.primary_key.columns
    ]

    if primary_key_names:
        sql += (
            " ORDER BY "
            + ", ".join(
                _quote_sqlite_identifier(
                    column_name
                )
                for column_name
                in primary_key_names
            )
        )

    rows = connection.execute(
        sql
    ).fetchall()

    return [
        dict(
            zip(
                column_names,
                row,
                strict=True,
            )
        )
        for row in rows
    ]


def _load_source_database(
    source_path: str | Path,
) -> tuple[
    Path,
    dict[str, list[dict]],
]:
    resolved_path = Path(
        source_path
    ).expanduser().resolve()

    if not resolved_path.exists():
        raise DataMigrationError(
            "Source SQLite database does not exist."
        )

    if not resolved_path.is_file():
        raise DataMigrationError(
            "Source SQLite path is not a file."
        )

    source_engine = _build_source_engine(
        resolved_path
    )

    try:
        validate_existing_schema(
            source_engine
        )
    except SchemaCompatibilityError as error:
        raise DataMigrationError(
            "Source SQLite schema is incompatible."
        ) from error
    finally:
        source_engine.dispose()

    database_uri = (
        resolved_path.as_uri()
        + "?mode=ro"
    )

    connection = sqlite3.connect(
        database_uri,
        uri=True,
    )

    try:
        integrity_result = connection.execute(
            "PRAGMA quick_check"
        ).fetchone()

        if (
            integrity_result is None
            or integrity_result[0] != "ok"
        ):
            raise DataMigrationError(
                "Source SQLite integrity check failed."
            )

        source_table_names = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        rows_by_table = {}

        for table in _APPLICATION_TABLES:
            if (
                table.name
                not in source_table_names
            ):
                if (
                    table.name
                    in _OPTIONAL_SOURCE_TABLE_NAMES
                ):
                    rows_by_table[
                        table.name
                    ] = []

                    continue

                raise DataMigrationError(
                    "Source SQLite schema "
                    "is incompatible."
                )

            rows_by_table[
                table.name
            ] = _read_source_rows(
                connection,
                table,
            )

    finally:
        connection.close()

    return (
        resolved_path,
        rows_by_table,
    )


def audit_sqlite_database(
    source_path: str | Path,
) -> MigrationReport:
    """Validate a source database without writing to a target."""
    (
        resolved_path,
        rows_by_table,
    ) = _load_source_database(
        source_path
    )

    row_counts = MappingProxyType(
        {
            table_name: len(rows)
            for table_name, rows
            in rows_by_table.items()
        }
    )

    return MigrationReport(
        source_path=resolved_path,
        target_backend="audit-only",
        row_counts=row_counts,
    )


def _ensure_target_is_empty(
    connection,
) -> None:
    nonempty_tables = []

    for table in _APPLICATION_TABLES:
        row_count = connection.execute(
            select(
                func.count()
            ).select_from(table)
        ).scalar_one()

        if int(row_count) > 0:
            nonempty_tables.append(
                table.name
            )

    if nonempty_tables:
        raise DataMigrationError(
            "Target database already contains "
            "application data: "
            + ", ".join(
                nonempty_tables
            )
        )


def _insert_rows(
    connection,
    table,
    rows: list[dict],
) -> None:
    if not rows:
        return

    connection.execute(
        insert(table),
        rows,
    )


def _prepare_initial_chat_rows(
    rows: list[dict],
) -> list[dict]:
    prepared_rows = []

    for row in rows:
        prepared_row = dict(row)

        for column_name in (
            _CHAT_RELATION_COLUMNS
        ):
            prepared_row[column_name] = None

        prepared_rows.append(
            prepared_row
        )

    return prepared_rows


def _restore_chat_relationships(
    connection,
    chat_rows: list[dict],
) -> None:
    for row in chat_rows:
        relationship_values = {
            column_name: row.get(
                column_name
            )
            for column_name in (
                _CHAT_RELATION_COLUMNS
            )
        }

        if not any(
            value is not None
            for value
            in relationship_values.values()
        ):
            continue

        connection.execute(
            update(chats)
            .where(
                chats.c.id == row["id"]
            )
            .values(
                **relationship_values
            )
        )


def _reset_postgresql_sequences(
    connection,
) -> None:
    for table in _SEQUENCE_TABLES:
        table_name = table.name

        connection.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(
                        '{table_name}',
                        'id'
                    ),
                    COALESCE(
                        (
                            SELECT MAX(id)
                            FROM {table_name}
                        ),
                        1
                    ),
                    EXISTS(
                        SELECT 1
                        FROM {table_name}
                    )
                )
                """
            )
        )


def _verify_target_counts(
    connection,
    expected_counts: dict[str, int],
) -> None:
    mismatches = []

    for table_name, expected_count in (
        expected_counts.items()
    ):
        table = _TABLE_BY_NAME[
            table_name
        ]

        actual_count = int(
            connection.execute(
                select(
                    func.count()
                ).select_from(table)
            ).scalar_one()
        )

        if actual_count != expected_count:
            mismatches.append(
                (
                    table_name,
                    expected_count,
                    actual_count,
                )
            )

    if mismatches:
        details = "; ".join(
            (
                f"{table_name}: "
                f"expected {expected}, "
                f"found {actual}"
            )
            for (
                table_name,
                expected,
                actual,
            ) in mismatches
        )

        raise DataMigrationError(
            "Target row-count verification failed: "
            + details
        )


def migrate_sqlite_database(
    source_path: str | Path,
    target_engine: Engine,
) -> MigrationReport:
    """Copy validated SQLite data into an empty initialized target."""
    (
        resolved_path,
        rows_by_table,
    ) = _load_source_database(
        source_path
    )

    expected_counts = {
        table_name: len(rows)
        for table_name, rows
        in rows_by_table.items()
    }

    initialize_schema(
        target_engine
    )

    with target_engine.begin() as connection:
        _ensure_target_is_empty(
            connection
        )

        for table in _INSERT_ORDER:
            rows = rows_by_table[
                table.name
            ]

            if table is chats:
                rows = (
                    _prepare_initial_chat_rows(
                        rows
                    )
                )

            _insert_rows(
                connection,
                table,
                rows,
            )

        _restore_chat_relationships(
            connection,
            rows_by_table[
                chats.name
            ],
        )

        if (
            target_engine.dialect.name
            == "postgresql"
        ):
            _reset_postgresql_sequences(
                connection
            )

        _verify_target_counts(
            connection,
            expected_counts,
        )

    return MigrationReport(
        source_path=resolved_path,
        target_backend=(
            target_engine.dialect.name
        ),
        row_counts=MappingProxyType(
            expected_counts
        ),
    )
