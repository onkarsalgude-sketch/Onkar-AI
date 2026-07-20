from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from app.database.db import (  # noqa: E402
    get_runtime_connection,
)
from app.services.memory_migration_service import (  # noqa: E402
    MemoryMigrationError,
    build_memory_migration_plan,
    execute_memory_migration,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Migrate local SQLite memory "
            "records into PostgreSQL."
        )
    )

    parser.add_argument(
        "--source-path",
        default=(
            "app/database/"
            "memory.db"
        ),
    )

    mode = (
        parser
        .add_mutually_exclusive_group(
            required=True
        )
    )

    mode.add_argument(
        "--dry-run",
        action="store_true",
    )

    mode.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
    )

    return parser


def print_plan(
    plan,
) -> None:
    print(
        "\nMemory migration plan:"
    )

    print(
        "  source records:",
        len(plan.records),
    )

    print(
        "  role counts:",
        dict(plan.role_counts),
    )

    print(
        "  blocking issues:",
        len(plan.issues),
    )

    for record in plan.records:
        print(
            "  record:",
            {
                "source_id": (
                    record.source_id
                ),
                "role": record.role,
                "content_length": len(
                    record.content
                ),
                "content_hash_prefix": (
                    record
                    .content_hash[:12]
                ),
            },
        )

    for issue in plan.issues:
        print(
            "  issue:",
            issue,
        )


def verify_target(
    connection,
    plan,
) -> None:
    cursor = connection.cursor()

    try:
        verified = 0

        for record in plan.records:
            cursor.execute(
                """
                SELECT role, content
                FROM public.memory
                WHERE legacy_source_id = ?
                """,
                (
                    record.source_id,
                ),
            )

            rows = cursor.fetchall()

            if len(rows) != 1:
                raise MemoryMigrationError()

            role = str(
                rows[0][0]
            )

            content = str(
                rows[0][1]
            )

            if (
                role != record.role
                or content
                != record.content
            ):
                raise MemoryMigrationError()

            expected_hash = (
                record.content_hash
            )

            actual_hash = (
                hashlib.sha256(
                    content.encode(
                        "utf-8"
                    )
                ).hexdigest()
            )

            if actual_hash != expected_hash:
                raise MemoryMigrationError()

            verified += 1

        if verified != len(
            plan.records
        ):
            raise MemoryMigrationError()

    finally:
        close = getattr(
            cursor,
            "close",
            None,
        )

        if callable(close):
            close()


def main() -> int:
    arguments = (
        build_parser()
        .parse_args()
    )

    if (
        arguments.execute
        and not arguments.yes
    ):
        raise SystemExit(
            "--yes is required "
            "with --execute."
        )

    source_path = Path(
        arguments.source_path
    ).expanduser().resolve(
        strict=False
    )

    if not source_path.is_file():
        raise SystemExit(
            "Source memory database "
            "was not found."
        )

    source_connection = (
        sqlite3.connect(
            source_path
        )
    )

    try:
        plan = (
            build_memory_migration_plan(
                source_connection
            )
        )

    finally:
        source_connection.close()

    print_plan(
        plan
    )

    if arguments.dry_run:
        print(
            "\nDry run complete. "
            "No PostgreSQL memory "
            "rows were changed."
        )

        return (
            0
            if plan.can_execute
            else 1
        )

    if not plan.can_execute:
        print(
            "\nMigration stopped because "
            "the plan contains issues.",
            file=sys.stderr,
        )

        return 1

    database_url = str(
        os.environ.get(
            "DATABASE_URL",
            "",
        )
    ).strip().casefold()

    if not database_url.startswith(
        (
            "postgres://",
            "postgresql://",
            "postgresql+psycopg://",
        )
    ):
        print(
            "\nMigration stopped because "
            "a PostgreSQL DATABASE_URL "
            "is required.",
            file=sys.stderr,
        )

        return 1

    target_connection = (
        get_runtime_connection(
            environ=dict(
                os.environ
            )
        )
    )

    try:
        report = (
            execute_memory_migration(
                plan,
                target_connection,
            )
        )

        verify_target(
            target_connection,
            plan,
        )

    except MemoryMigrationError:
        print(
            "\nMemory migration failed.",
            file=sys.stderr,
        )

        return 1

    finally:
        close = getattr(
            target_connection,
            "close",
            None,
        )

        if callable(close):
            close()

    print(
        "\nMemory migration: PASSED"
    )

    print(
        "  migrated records:",
        report.migrated_records,
    )

    print(
        "  user records:",
        report.user_records,
    )

    print(
        "  assistant records:",
        report.assistant_records,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
