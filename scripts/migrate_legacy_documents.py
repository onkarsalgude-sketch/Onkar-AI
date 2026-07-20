from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from app.config.database import (  # noqa: E402
    load_database_settings,
)
from app.config.storage import (  # noqa: E402
    load_document_storage_settings,
)
from app.database.db import (  # noqa: E402
    get_runtime_connection,
)
from app.services.document_migration_service import (  # noqa: E402
    DocumentMigrationError,
    build_document_migration_plan,
    execute_document_migration,
)
from app.services.document_object_service import (  # noqa: E402
    get_document_storage,
)


def _build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy Onkar-AI PDF "
            "files into durable document storage."
        )
    )

    parser.add_argument(
        "--sqlite-path",
        default=(
            "app/database/chat_history.db"
        ),
        help=(
            "SQLite database path when "
            "DATABASE_URL is not configured."
        ),
    )

    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        help=(
            "Legacy upload root. May be "
            "specified multiple times."
        ),
    )

    parser.add_argument(
        "--include-non-ready",
        action="store_true",
        help=(
            "Include document records whose "
            "status is not ready."
        ),
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and report without "
            "changing storage or database data."
        ),
    )

    mode.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Perform the actual migration."
        ),
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Confirm the actual migration."
        ),
    )

    return parser


def _record_label(record) -> str:
    return (
        f"chat={record.chat_id} "
        f"document={record.document_id} "
        f"filename={record.filename}"
    )


def _print_plan(plan) -> None:
    print("\nMigration preflight:")
    print(
        "  total rows:",
        plan.total_rows,
    )
    print(
        "  ready to migrate:",
        len(plan.ready),
    )
    print(
        "  already migrated:",
        len(plan.already_migrated),
    )
    print(
        "  missing source PDFs:",
        len(plan.missing),
    )
    print(
        "  invalid documents:",
        len(plan.invalid),
    )
    print(
        "  skipped by status:",
        len(plan.skipped_status),
    )

    if plan.ready:
        print("\nReady:")

        for item in plan.ready:
            print(
                " ",
                _record_label(
                    item.record
                ),
            )
            print(
                "    source:",
                item.source_path,
            )
            print(
                "    target:",
                item.target_key,
            )

    if plan.missing:
        print("\nMissing:")

        for issue in plan.missing:
            print(
                " ",
                _record_label(
                    issue.record
                ),
            )
            print(
                "    reason:",
                issue.reason,
            )

            for attempted_path in (
                issue.attempted_paths
            ):
                print(
                    "    checked:",
                    attempted_path,
                )

    if plan.invalid:
        print("\nInvalid:")

        for issue in plan.invalid:
            print(
                " ",
                _record_label(
                    issue.record
                ),
            )
            print(
                "    reason:",
                issue.reason,
            )


def main() -> int:
    parser = _build_parser()
    arguments = parser.parse_args()

    if (
        arguments.execute
        and not arguments.yes
    ):
        parser.error(
            "--yes is required with --execute."
        )

    environment = dict(
        os.environ
    )

    database_settings = (
        load_database_settings(
            environment,
            default_sqlite_path=(
                arguments.sqlite_path
            ),
        )
    )

    storage_settings = (
        load_document_storage_settings()
    )

    source_roots = [
        Path(value)
        for value in arguments.source_root
    ]

    if not source_roots:
        source_roots = [
            Path("storage/uploads"),
            Path("storage/pdfs"),
        ]

    print(
        "Database target:",
        database_settings.safe_target,
    )

    print(
        "Storage target:",
        storage_settings.safe_target,
    )

    connection = get_runtime_connection(
        arguments.sqlite_path,
        environ=environment,
    )

    try:
        storage = get_document_storage()

        plan = build_document_migration_plan(
            connection,
            storage,
            source_roots=source_roots,
            include_non_ready=(
                arguments.include_non_ready
            ),
        )

        _print_plan(
            plan
        )

        if arguments.dry_run:
            print(
                "\nDry run complete. "
                "No objects or database rows "
                "were changed."
            )

            return 0

        if not plan.can_execute:
            raise DocumentMigrationError(
                "Actual migration stopped "
                "because preflight found "
                "missing or invalid documents."
            )

        report = execute_document_migration(
            plan,
            connection,
            storage,
        )

        print("\nMigration: PASSED")
        print(
            "  migrated:",
            report.migrated,
        )
        print(
            "  already migrated:",
            report.already_migrated,
        )
        print(
            "  newly created objects:",
            report.created_objects,
        )

        return 0

    except DocumentMigrationError as error:
        print(
            f"\nMigration stopped: {error}",
            file=sys.stderr,
        )

        return 1

    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
