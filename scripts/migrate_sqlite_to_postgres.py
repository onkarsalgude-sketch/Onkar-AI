"""Run an explicit SQLite-to-PostgreSQL migration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from app.config.database import (  # noqa: E402
    DatabaseConfigurationError,
    load_database_settings,
)
from app.database.data_migration import (  # noqa: E402
    DataMigrationError,
    audit_sqlite_database,
    migrate_sqlite_database,
)
from app.database.engine import (  # noqa: E402
    build_database_engine,
)


def _build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Validate and migrate the Onkar-AI "
            "SQLite chat database to PostgreSQL."
        )
    )

    parser.add_argument(
        "--sqlite-path",
        default=(
            "app/database/chat_history.db"
        ),
        help=(
            "Path to the source SQLite database."
        ),
    )

    parser.add_argument(
        "--database-url",
        help=(
            "Target PostgreSQL URL. "
            "Defaults to DATABASE_URL."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate the SQLite database "
            "without connecting to PostgreSQL."
        ),
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Confirm execution of the actual migration."
        ),
    )

    return parser


def _print_counts(report):
    print("\nRow counts:")

    for table_name, row_count in (
        report.row_counts.items()
    ):
        print(
            f"  {table_name}: {row_count}"
        )

    print(
        f"  TOTAL: {report.total_rows}"
    )


def main() -> int:
    parser = _build_parser()
    arguments = parser.parse_args()

    try:
        audit_report = (
            audit_sqlite_database(
                arguments.sqlite_path
            )
        )

        print(
            "Source database:",
            audit_report.source_path,
        )
        print(
            "SQLite validation: PASSED"
        )

        _print_counts(
            audit_report
        )

        if arguments.dry_run:
            print(
                "\nDry run complete. "
                "No target database was changed."
            )
            return 0

        if not arguments.yes:
            parser.error(
                "--yes is required for "
                "the actual migration."
            )

        environment = dict(
            os.environ
        )

        if arguments.database_url:
            environment[
                "DATABASE_URL"
            ] = arguments.database_url

        environment[
            "DATABASE_REQUIRE_PERSISTENCE"
        ] = "true"

        settings = load_database_settings(
            environment,
            default_sqlite_path=(
                arguments.sqlite_path
            ),
        )

        if not settings.is_postgresql:
            raise DataMigrationError(
                "The target must be PostgreSQL."
            )

        print(
            "\nTarget database:",
            settings.safe_target,
        )

        target_engine = (
            build_database_engine(
                settings
            )
        )

        try:
            report = migrate_sqlite_database(
                arguments.sqlite_path,
                target_engine,
            )
        finally:
            target_engine.dispose()

        print(
            "\nMigration: PASSED"
        )
        print(
            "Target backend:",
            report.target_backend,
        )

        _print_counts(
            report
        )

        print(
            "\nSQLite-to-PostgreSQL migration "
            "completed successfully."
        )

        return 0

    except (
        DataMigrationError,
        DatabaseConfigurationError,
    ) as error:
        print(
            f"\nMigration stopped: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
