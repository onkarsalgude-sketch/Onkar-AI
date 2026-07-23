from __future__ import annotations

import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import history_service


class MessageAgentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name)
            / "message-agent-history.db"
        )
        self.db_path_patch = patch.object(
            history_service,
            "DB_PATH",
            str(self.database_path),
        )
        self.db_path_patch.start()
        history_service.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temporary_directory.cleanup()

    def test_save_and_load_agent_id(self):
        chat_id = history_service.create_chat(
            "Agent History"
        )
        history_service.save_message(
            chat_id,
            "assistant",
            "Study response",
            model_id="model-a",
            agent_id="study",
        )

        messages = history_service.get_messages(
            chat_id
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0]["agent_id"],
            "study",
        )
        self.assertEqual(
            messages[0]["model_id"],
            "model-a",
        )

    def test_get_message_returns_agent_id(self):
        chat_id = history_service.create_chat(
            "Single Message"
        )
        history_service.save_message(
            chat_id,
            "assistant",
            "Coding response",
            agent_id="coding",
        )
        stored = history_service.get_messages(
            chat_id
        )[0]

        message = history_service.get_message(
            chat_id,
            stored["id"],
        )

        self.assertIsNotNone(message)
        self.assertEqual(
            message["agent_id"],
            "coding",
        )

    def test_legacy_row_returns_none_agent_id(self):
        chat_id = history_service.create_chat(
            "Legacy Message"
        )
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            connection.execute(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    model_id,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    "assistant",
                    "Legacy response",
                    "2026-07-23T12:00:00",
                    "[]",
                    "legacy-model",
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        messages = history_service.get_messages(
            chat_id
        )

        self.assertIsNone(
            messages[0]["agent_id"]
        )

        message = history_service.get_message(
            chat_id,
            messages[0]["id"],
        )
        self.assertIsNone(
            message["agent_id"]
        )

    def test_old_save_message_call_remains_compatible(self):
        chat_id = history_service.create_chat(
            "Backward Compatible"
        )
        history_service.save_message(
            chat_id,
            "user",
            "Legacy caller",
        )

        message = history_service.get_messages(
            chat_id
        )[0]

        self.assertIn("agent_id", message)
        self.assertIsNone(
            message["agent_id"]
        )

    def test_branch_copy_query_preserves_agent_id(self):
        source = inspect.getsource(
            history_service.create_chat_branch
        )
        compact = " ".join(
            source.split()
        )
        expected_columns = (
            "sources_json, model_id, "
            "agent_id, attachment_json"
        )

        self.assertGreaterEqual(
            compact.count(expected_columns),
            2,
        )


if __name__ == "__main__":
    unittest.main()
