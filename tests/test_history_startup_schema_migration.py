from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import (
    MagicMock,
    call,
    patch,
)

from app.services import history_service


ROOT = Path(__file__).resolve().parents[1]


class HistoryStartupSchemaMigrationTests(
    unittest.TestCase
):
    def test_postgresql_startup_runs_schema_initializer(
        self,
    ):
        settings = SimpleNamespace(
            is_sqlite=False
        )

        engine = MagicMock()

        with (
            patch.object(
                history_service,
                "load_database_settings",
                return_value=settings,
            ) as load_settings,
            patch.object(
                history_service,
                "build_database_engine",
                return_value=engine,
            ) as build_engine,
            patch.object(
                history_service,
                "initialize_schema",
            ) as initialize,
            patch.object(
                history_service,
                "_legacy_init_db",
            ) as legacy,
        ):
            result = history_service.init_db()

        self.assertIsNone(
            result
        )

        load_settings.assert_called_once_with(
            default_sqlite_path=(
                history_service.DB_PATH
            ),
        )

        build_engine.assert_called_once_with(
            settings
        )

        initialize.assert_called_once_with(
            engine
        )

        legacy.assert_not_called()
        engine.dispose.assert_called_once_with()

    def test_sqlite_runs_legacy_backfill_before_schema_initializer(
        self,
    ):
        settings = SimpleNamespace(
            is_sqlite=True
        )

        engine = MagicMock()
        ordered_calls = MagicMock()

        legacy = MagicMock()
        initialize = MagicMock()

        ordered_calls.attach_mock(
            legacy,
            "legacy",
        )

        ordered_calls.attach_mock(
            initialize,
            "initialize",
        )

        with (
            patch.object(
                history_service,
                "load_database_settings",
                return_value=settings,
            ),
            patch.object(
                history_service,
                "build_database_engine",
                return_value=engine,
            ),
            patch.object(
                history_service,
                "_legacy_init_db",
                legacy,
            ),
            patch.object(
                history_service,
                "initialize_schema",
                initialize,
            ),
        ):
            history_service.init_db()

        self.assertEqual(
            ordered_calls.mock_calls,
            [
                call.legacy(),
                call.initialize(engine),
            ],
        )

        engine.dispose.assert_called_once_with()

    def test_initializer_failure_disposes_engine_and_propagates(
        self,
    ):
        settings = SimpleNamespace(
            is_sqlite=False
        )

        engine = MagicMock()

        with (
            patch.object(
                history_service,
                "load_database_settings",
                return_value=settings,
            ),
            patch.object(
                history_service,
                "build_database_engine",
                return_value=engine,
            ),
            patch.object(
                history_service,
                "initialize_schema",
                side_effect=RuntimeError(
                    "migration failed"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "migration failed",
            ):
                history_service.init_db()

        engine.dispose.assert_called_once_with()

    def test_portable_init_has_no_validate_only_version_gate(
        self,
    ):
        source_path = (
            ROOT
            / "app"
            / "services"
            / "history_service.py"
        )

        source = source_path.read_text(
            encoding="utf-8-sig"
        )

        tree = ast.parse(
            source,
            filename=str(source_path),
        )

        init_nodes = [
            node
            for node in tree.body
            if (
                isinstance(
                    node,
                    ast.FunctionDef,
                )
                and node.name == "init_db"
            )
        ]

        self.assertEqual(
            len(init_nodes),
            2,
        )

        portable_init = max(
            init_nodes,
            key=lambda node: node.lineno,
        )

        portable_source = (
            ast.get_source_segment(
                source,
                portable_init,
            )
        )

        self.assertIsNotNone(
            portable_source
        )

        self.assertIn(
            "initialize_schema",
            portable_source,
        )

        self.assertNotIn(
            "get_schema_version",
            portable_source,
        )

        self.assertNotIn(
            "validate_existing_schema",
            portable_source,
        )

        self.assertNotIn(
            "raise SchemaVersionError",
            portable_source,
        )


if __name__ == "__main__":
    unittest.main()
