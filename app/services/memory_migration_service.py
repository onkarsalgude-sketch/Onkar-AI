"""Idempotent SQLite-to-PostgreSQL memory migration."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from app.database.memory_schema import (
    MEMORY_TABLE_NAME,
    MemorySchemaError,
    initialize_memory_schema,
)


class MemoryMigrationError(
    RuntimeError
):
    """Raised without leaking memory content or credentials."""

    def __init__(self):
        super().__init__(
            "Memory migration failed."
        )


@dataclass(frozen=True)
class LegacyMemoryRecord:
    source_id: int
    role: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class MemoryMigrationPlan:
    records: tuple[
        LegacyMemoryRecord,
        ...,
    ]

    role_counts: tuple[
        tuple[str, int],
        ...,
    ]

    issues: tuple[
        str,
        ...,
    ]

    @property
    def can_execute(self) -> bool:
        return (
            bool(self.records)
            and not self.issues
        )


@dataclass(frozen=True)
class MemoryMigrationReport:
    migrated_records: int
    user_records: int
    assistant_records: int


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


def _content_hash(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def build_memory_migration_plan(
    source_connection,
) -> MemoryMigrationPlan:
    cursor = source_connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id, role, content
            FROM memory
            ORDER BY id
            """
        )

        rows = cursor.fetchall()

    except Exception as error:
        raise (
            MemoryMigrationError()
        ) from error

    finally:
        _close_safely(
            cursor
        )

    records = []
    issues = []
    seen_ids = set()

    for row in rows:
        try:
            source_id = int(
                row[0]
            )
        except (
            TypeError,
            ValueError,
        ):
            issues.append(
                "A source memory ID is invalid."
            )
            continue

        role = str(
            row[1] or ""
        ).strip()

        content = str(
            row[2] or ""
        ).strip()

        if source_id <= 0:
            issues.append(
                "A source memory ID is invalid."
            )
            continue

        if source_id in seen_ids:
            issues.append(
                "Duplicate source memory IDs exist."
            )
            continue

        seen_ids.add(
            source_id
        )

        if (
            not role
            or len(role) > 100
        ):
            issues.append(
                "A source memory role is invalid."
            )
            continue

        if not content:
            issues.append(
                "A source memory content value is empty."
            )
            continue

        records.append(
            LegacyMemoryRecord(
                source_id=source_id,
                role=role,
                content=content,
                content_hash=(
                    _content_hash(
                        content
                    )
                ),
            )
        )

    role_counter = Counter(
        record.role
        for record in records
    )

    return MemoryMigrationPlan(
        records=tuple(
            records
        ),
        role_counts=tuple(
            sorted(
                (
                    str(role),
                    int(count),
                )
                for role, count
                in role_counter.items()
            )
        ),
        issues=tuple(
            issues
        ),
    )


def execute_memory_migration(
    plan: MemoryMigrationPlan,
    target_connection,
) -> MemoryMigrationReport:
    if not plan.can_execute:
        raise MemoryMigrationError()

    try:
        initialize_memory_schema(
            target_connection,
            is_postgresql=True,
        )

    except MemorySchemaError as error:
        raise (
            MemoryMigrationError()
        ) from error

    cursor = target_connection.cursor()

    try:
        for record in plan.records:
            cursor.execute(
                f"""
                INSERT INTO
                public.{MEMORY_TABLE_NAME} (
                    role,
                    content,
                    legacy_source_id
                )
                VALUES (?, ?, ?)
                ON CONFLICT (
                    legacy_source_id
                )
                DO UPDATE SET
                    role = EXCLUDED.role,
                    content = EXCLUDED.content
                """,
                (
                    record.role,
                    record.content,
                    record.source_id,
                ),
            )

        for record in plan.records:
            cursor.execute(
                f"""
                SELECT role, content
                FROM public.{MEMORY_TABLE_NAME}
                WHERE legacy_source_id = ?
                """,
                (
                    record.source_id,
                ),
            )

            row = cursor.fetchone()

            if row is None:
                raise MemoryMigrationError()

            if (
                str(row[0]) != record.role
                or str(row[1])
                != record.content
            ):
                raise MemoryMigrationError()

        target_connection.commit()

    except Exception as error:
        try:
            target_connection.rollback()
        except Exception:
            pass

        if isinstance(
            error,
            MemoryMigrationError,
        ):
            raise

        raise (
            MemoryMigrationError()
        ) from error

    finally:
        _close_safely(
            cursor
        )

    role_counts = dict(
        plan.role_counts
    )

    return MemoryMigrationReport(
        migrated_records=len(
            plan.records
        ),
        user_records=int(
            role_counts.get(
                "user",
                0,
            )
        ),
        assistant_records=int(
            role_counts.get(
                "assistant",
                0,
            )
        ),
    )
