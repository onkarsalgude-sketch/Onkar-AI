"""Explicit schema initialization and version validation."""

from datetime import datetime, timezone
import re

from sqlalchemy import insert, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.database.schema import (
    EXPECTED_TABLE_NAMES,
    SCHEMA_VERSION,
    branch_merge_message_mappings,
    branch_merge_operations,
    chats,
    create_schema,
    documents,
    document_recovery_runs,
    folders,
    message_bookmarks,
    messages,
    schema_migrations,
    system_incident_alert_outbox,
    system_incidents,
)


class SchemaVersionError(RuntimeError):
    """Raised when an explicit database migration is required."""

    def __init__(self):
        super().__init__(
            "Database schema version is incompatible."
        )


class SchemaCompatibilityError(RuntimeError):
    """Raised when an existing schema cannot be safely adopted."""

    def __init__(self):
        super().__init__(
            "Existing database schema is incompatible."
        )


_SCHEMA_V1_APPLICATION_TABLES = (
    folders,
    chats,
    messages,
    message_bookmarks,
    documents,
    branch_merge_operations,
    branch_merge_message_mappings,
)

_SCHEMA_V2_APPLICATION_TABLES = (
    *_SCHEMA_V1_APPLICATION_TABLES,
    document_recovery_runs,
)


_SCHEMA_V3_APPLICATION_TABLES = (
    *_SCHEMA_V2_APPLICATION_TABLES,
    system_incidents,
)


_APPLICATION_TABLES = (
    *_SCHEMA_V3_APPLICATION_TABLES,
    system_incident_alert_outbox,
)

_SCHEMA_V1_VERSIONED_TABLE_NAMES = frozenset(
    {
        schema_migrations.name,
        *(
            table.name
            for table
            in _SCHEMA_V1_APPLICATION_TABLES
        ),
    }
)


_SCHEMA_V2_VERSIONED_TABLE_NAMES = frozenset(
    {
        schema_migrations.name,
        *(
            table.name
            for table
            in _SCHEMA_V2_APPLICATION_TABLES
        ),
    }
)


_SCHEMA_V3_VERSIONED_TABLE_NAMES = frozenset(
    {
        schema_migrations.name,
        *(
            table.name
            for table
            in _SCHEMA_V3_APPLICATION_TABLES
        ),
    }
)

_LEGACY_TABLE_NAMES = frozenset(
    table.name
    for table in _SCHEMA_V1_APPLICATION_TABLES
)

_REQUIRED_UNIQUE_COLUMN_SETS = {
    folders.name: {
        frozenset({"name"}),
    },
    message_bookmarks.name: {
        frozenset({"message_id"}),
    },
    documents.name: {
        frozenset(
            {
                "chat_id",
                "filename",
            }
        ),
    },
    branch_merge_operations.name: {
        frozenset({"idempotency_key"}),
    },
    branch_merge_message_mappings.name: {
        frozenset(
            {
                "created_parent_message_id",
            }
        ),
        frozenset(
            {
                "merge_operation_id",
                "source_branch_message_id",
            }
        ),
        frozenset(
            {
                "branch_chat_id",
                "parent_chat_id",
                "source_branch_message_id",
            }
        ),
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_recorded_versions(
    engine: Engine,
) -> tuple[int, ...]:
    inspector = inspect(engine)

    if schema_migrations.name not in (
        inspector.get_table_names()
    ):
        return ()

    with engine.connect() as connection:
        rows = connection.execute(
            select(
                schema_migrations.c.version
            ).order_by(
                schema_migrations.c.version
            )
        ).scalars()

        return tuple(
            int(version)
            for version in rows
        )


def get_schema_version(engine: Engine) -> int:
    """Return zero when the schema has not been versioned."""
    versions = _read_recorded_versions(engine)

    if not versions:
        return 0

    return max(versions)


def _validate_recorded_version(
    versions: tuple[int, ...],
) -> None:
    normalized = tuple(
        int(version)
        for version in versions
    )

    if (
        len(set(normalized))
        != len(normalized)
    ):
        raise SchemaVersionError()

    if normalized != tuple(
        sorted(normalized)
    ):
        raise SchemaVersionError()

    valid_version_sets = {
        (),
        (1,),
        (2,),
        (3,),
        (SCHEMA_VERSION,),
        (
            1,
            2,
        ),
        (
            2,
            3,
        ),
        (
            3,
            SCHEMA_VERSION,
        ),
        (
            1,
            2,
            3,
        ),
        (
            2,
            3,
            SCHEMA_VERSION,
        ),
        (
            1,
            2,
            3,
            SCHEMA_VERSION,
        ),
    }

    if normalized not in valid_version_sets:
        raise SchemaVersionError()

def _normalize_sql_definition(
    value: str,
) -> str:
    return re.sub(
        r'[\s"`\[\]]+',
        "",
        str(value).casefold(),
    )


def _quote_sqlite_identifier(
    value: str,
) -> str:
    return (
        '"'
        + str(value).replace('"', '""')
        + '"'
    )


def _sqlite_unique_metadata(
    engine: Engine,
    table_name: str,
) -> tuple[
    set[frozenset[str]],
    tuple[str, ...],
]:
    unique_column_sets = set()
    index_definitions = []

    quoted_table = _quote_sqlite_identifier(
        table_name
    )

    with engine.connect() as connection:
        index_rows = connection.exec_driver_sql(
            f"PRAGMA index_list({quoted_table})"
        ).fetchall()

        for index_row in index_rows:
            index_name = index_row[1]
            is_unique = bool(index_row[2])

            if not is_unique:
                continue

            quoted_index = (
                _quote_sqlite_identifier(
                    index_name
                )
            )

            column_rows = (
                connection.exec_driver_sql(
                    f"PRAGMA index_info("
                    f"{quoted_index})"
                ).fetchall()
            )

            column_names = [
                row[2]
                for row in column_rows
            ]

            if (
                column_names
                and all(column_names)
            ):
                unique_column_sets.add(
                    frozenset(column_names)
                )

            definition_row = (
                connection.exec_driver_sql(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE type = 'index'
                      AND name = ?
                    """,
                    (index_name,),
                ).fetchone()
            )

            if (
                definition_row is not None
                and definition_row[0]
            ):
                index_definitions.append(
                    _normalize_sql_definition(
                        definition_row[0]
                    )
                )

    return (
        unique_column_sets,
        tuple(index_definitions),
    )


def _generic_unique_metadata(
    inspector,
    table_name: str,
) -> tuple[
    set[frozenset[str]],
    tuple[str, ...],
]:
    unique_column_sets = set()
    index_definitions = []

    for constraint in (
        inspector.get_unique_constraints(
            table_name
        )
    ):
        column_names = (
            constraint.get(
                "column_names"
            )
            or []
        )

        if (
            column_names
            and all(column_names)
        ):
            unique_column_sets.add(
                frozenset(column_names)
            )

    for index in inspector.get_indexes(
        table_name
    ):
        if not index.get("unique"):
            continue

        column_names = (
            index.get("column_names")
            or []
        )

        if (
            column_names
            and all(column_names)
        ):
            unique_column_sets.add(
                frozenset(column_names)
            )

        expressions = (
            index.get("expressions")
            or []
        )

        if expressions:
            index_definitions.append(
                _normalize_sql_definition(
                    " ".join(
                        str(expression)
                        for expression
                        in expressions
                    )
                )
            )

    return (
        unique_column_sets,
        tuple(index_definitions),
    )


def _collect_unique_metadata(
    engine: Engine,
    inspector,
    table_name: str,
) -> tuple[
    set[frozenset[str]],
    tuple[str, ...],
]:
    if engine.dialect.name == "sqlite":
        return _sqlite_unique_metadata(
            engine,
            table_name,
        )

    return _generic_unique_metadata(
        inspector,
        table_name,
    )


def _expression_unique_requirement_met(
    table_name: str,
    required_columns: frozenset[str],
    definitions: tuple[str, ...],
) -> bool:
    if (
        table_name == folders.name
        and required_columns
        == frozenset({"name"})
    ):
        return any(
            "lower(" in definition
            and "name" in definition
            for definition in definitions
        )

    if (
        table_name == documents.name
        and required_columns
        == frozenset(
            {
                "chat_id",
                "filename",
            }
        )
    ):
        return any(
            "chat_id" in definition
            and "lower(" in definition
            and "filename" in definition
            for definition in definitions
        )

    return False


def _required_unique_sets_are_present(
    engine: Engine,
    inspector,
    table_name: str,
    required_unique_sets: set[
        frozenset[str]
    ],
) -> bool:
    (
        actual_unique_sets,
        index_definitions,
    ) = _collect_unique_metadata(
        engine,
        inspector,
        table_name,
    )

    for required_columns in (
        required_unique_sets
    ):
        if required_columns in (
            actual_unique_sets
        ):
            continue

        if _expression_unique_requirement_met(
            table_name,
            required_columns,
            index_definitions,
        ):
            continue

        return False

    return True


def validate_existing_schema(
    engine: Engine,
    *,
    expected_version: int | None = None,
) -> None:
    """Validate an existing application schema safely."""
    inspector = inspect(engine)

    table_names = set(
        inspector.get_table_names()
    )

    present_application_tables = (
        table_names
        & EXPECTED_TABLE_NAMES
    )

    if not present_application_tables:
        return

    version_table_present = (
        schema_migrations.name
        in present_application_tables
    )

    if version_table_present:
        if expected_version is None:
            recorded_versions = (
                _read_recorded_versions(
                    engine
                )
            )

            _validate_recorded_version(
                recorded_versions
            )

            if recorded_versions:
                resolved_version = max(
                    recorded_versions
                )
            elif (
                system_incident_alert_outbox.name
                in table_names
            ):
                resolved_version = 4
            elif (
                system_incidents.name
                in table_names
            ):
                resolved_version = 3
            elif (
                document_recovery_runs.name
                in table_names
            ):
                resolved_version = 2
            else:
                resolved_version = 1
        else:
            resolved_version = int(
                expected_version
            )

        if resolved_version == 1:
            required_table_names = (
                _SCHEMA_V1_VERSIONED_TABLE_NAMES
            )

            tables_to_validate = (
                *_SCHEMA_V1_APPLICATION_TABLES,
                schema_migrations,
            )
        elif resolved_version == 2:
            required_table_names = (
                _SCHEMA_V2_VERSIONED_TABLE_NAMES
            )

            tables_to_validate = (
                *_SCHEMA_V2_APPLICATION_TABLES,
                schema_migrations,
            )
        elif resolved_version == 3:
            required_table_names = (
                _SCHEMA_V3_VERSIONED_TABLE_NAMES
            )

            tables_to_validate = (
                *_SCHEMA_V3_APPLICATION_TABLES,
                schema_migrations,
            )
        elif (
            resolved_version
            == SCHEMA_VERSION
        ):
            required_table_names = (
                EXPECTED_TABLE_NAMES
            )

            tables_to_validate = (
                *_APPLICATION_TABLES,
                schema_migrations,
            )
        else:
            raise SchemaVersionError()
    else:
        if expected_version is not None:
            raise SchemaCompatibilityError()

        required_table_names = (
            _LEGACY_TABLE_NAMES
        )

        tables_to_validate = (
            _SCHEMA_V1_APPLICATION_TABLES
        )

    missing_tables = (
        required_table_names
        - present_application_tables
    )

    if missing_tables:
        raise SchemaCompatibilityError()

    for table in tables_to_validate:
        actual_columns = {
            column["name"]
            for column in inspector.get_columns(
                table.name
            )
        }

        required_columns = set(
            table.c.keys()
        )

        if not required_columns.issubset(
            actual_columns
        ):
            raise SchemaCompatibilityError()

        expected_primary_key = tuple(
            column.name
            for column
            in table.primary_key.columns
        )

        actual_primary_key = tuple(
            inspector.get_pk_constraint(
                table.name
            ).get(
                "constrained_columns"
            )
            or ()
        )

        if (
            actual_primary_key
            != expected_primary_key
        ):
            raise SchemaCompatibilityError()

        required_unique_sets = (
            _REQUIRED_UNIQUE_COLUMN_SETS.get(
                table.name,
                set(),
            )
        )

        if (
            required_unique_sets
            and not (
                _required_unique_sets_are_present(
                    engine,
                    inspector,
                    table.name,
                    required_unique_sets,
                )
            )
        ):
            raise SchemaCompatibilityError()

def initialize_schema(
    engine: Engine,
) -> int:
    """Create, adopt, or migrate the current schema safely."""
    existing_versions = (
        _read_recorded_versions(
            engine
        )
    )

    _validate_recorded_version(
        existing_versions
    )

    if existing_versions:
        validate_existing_schema(
            engine,
            expected_version=max(
                existing_versions
            ),
        )
    else:
        validate_existing_schema(
            engine
        )

    create_schema(engine)

    validate_existing_schema(
        engine,
        expected_version=SCHEMA_VERSION,
    )

    try:
        with engine.begin() as connection:
            recorded_versions = tuple(
                int(version)
                for version in connection.execute(
                    select(
                        schema_migrations.c.version
                    ).order_by(
                        schema_migrations.c.version
                    )
                ).scalars()
            )

            _validate_recorded_version(
                recorded_versions
            )

            if not recorded_versions:
                connection.execute(
                    insert(
                        schema_migrations
                    ).values(
                        version=SCHEMA_VERSION,
                        description=(
                            "Initial complete "
                            "application schema"
                        ),
                        applied_at=_utc_now_iso(),
                    )
                )
            else:
                latest_version = max(
                    recorded_versions
                )

                if latest_version < 2:
                    connection.execute(
                        insert(
                            schema_migrations
                        ).values(
                            version=2,
                            description=(
                                "Add document recovery "
                                "run history"
                            ),
                            applied_at=_utc_now_iso(),
                        )
                    )

                if latest_version < 3:
                    connection.execute(
                        insert(
                            schema_migrations
                        ).values(
                            version=3,
                            description=(
                                "Add durable system "
                                "incident history"
                            ),
                            applied_at=_utc_now_iso(),
                        )
                    )

                if latest_version < SCHEMA_VERSION:
                    connection.execute(
                        insert(
                            schema_migrations
                        ).values(
                            version=SCHEMA_VERSION,
                            description=(
                                "Add durable incident "
                                "alert outbox"
                            ),
                            applied_at=_utc_now_iso(),
                        )
                    )
    except IntegrityError:
        final_versions = (
            _read_recorded_versions(
                engine
            )
        )

        _validate_recorded_version(
            final_versions
        )

        if (
            not final_versions
            or max(final_versions)
            != SCHEMA_VERSION
        ):
            raise

    final_versions = (
        _read_recorded_versions(
            engine
        )
    )

    _validate_recorded_version(
        final_versions
    )

    if (
        not final_versions
        or max(final_versions)
        != SCHEMA_VERSION
    ):
        raise SchemaVersionError()

    validate_existing_schema(
        engine,
        expected_version=SCHEMA_VERSION,
    )

    return SCHEMA_VERSION
