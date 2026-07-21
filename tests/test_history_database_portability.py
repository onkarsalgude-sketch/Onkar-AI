import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.database.migrations import (
    SchemaVersionError,
)
from app.services import history_service


class HistoryDatabasePortabilityTests(
    unittest.TestCase
):
    def test_sqlite_history_workflow_still_works(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "history.db"
            )

            original_path = (
                history_service.DB_PATH
            )

            history_service.DB_PATH = str(
                database_path
            )

            try:
                with patch.dict(
                    os.environ,
                    {
                        "DATABASE_URL": "",
                        "SQLITE_DB_PATH": "",
                        "DATABASE_REQUIRE_PERSISTENCE": (
                            "false"
                        ),
                    },
                    clear=False,
                ):
                    history_service.init_db()

                    folder = (
                        history_service
                        .create_folder(
                            "Portable"
                        )
                    )

                    chat_id = (
                        history_service
                        .create_chat(
                            "History Test"
                        )
                    )

                    history_service.save_message(
                        chat_id,
                        "user",
                        "Hello portable database",
                    )

                    moved = (
                        history_service
                        .move_chat_to_folder(
                            chat_id,
                            folder["id"],
                        )
                    )

                    messages = (
                        history_service
                        .get_messages(
                            chat_id
                        )
                    )

                self.assertTrue(moved)
                self.assertEqual(
                    messages[0]["content"],
                    "Hello portable database",
                )

            finally:
                history_service.DB_PATH = (
                    original_path
                )

    def test_postgresql_init_runs_safe_schema_migration(
        self,
    ):
        settings = MagicMock(
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

        initialize.assert_called_once_with(
            engine
        )

        legacy.assert_not_called()

        engine.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
