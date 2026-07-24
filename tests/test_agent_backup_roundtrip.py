from __future__ import annotations

import unittest
from unittest import mock

from app.models.chat import (
    ChatBackupImportRequest,
    ChatBackupMessage,
)
from app.services import export_service
from app.services import history_service


class AgentBackupRoundTripTests(unittest.TestCase):
    def test_backup_message_model_accepts_optional_agent_id(self):
        explicit = ChatBackupMessage(
            role="assistant",
            content="Study answer",
            agent_id="study",
        )

        legacy = ChatBackupMessage(
            role="assistant",
            content="Legacy answer",
        )

        self.assertEqual(
            explicit.agent_id,
            "study",
        )
        self.assertIsNone(
            legacy.agent_id
        )

    def test_export_serializes_agent_id_without_inventing_legacy_value(self):
        with mock.patch.object(
            export_service,
            "get_messages",
            return_value=[
                {
                    "id": 1,
                    "role": "assistant",
                    "content": "Study answer",
                    "model_id": "model-a",
                    "agent_id": "study",
                    "created_at": None,
                    "attachment": None,
                    "sources": [],
                },
                {
                    "id": 2,
                    "role": "assistant",
                    "content": "Legacy answer",
                    "model_id": "model-a",
                    "agent_id": None,
                    "created_at": None,
                    "attachment": None,
                    "sources": [],
                },
            ],
        ):
            messages = (
                export_service
                ._build_backup_messages(7)
            )

        self.assertEqual(
            messages[0]["agent_id"],
            "study",
        )
        self.assertIsNone(
            messages[1]["agent_id"]
        )

    def test_import_request_preserves_agent_id_and_legacy_null(self):
        request = ChatBackupImportRequest(
            schema_version=1,
            application="Onkar AI",
            chat={
                "title": "Restored",
            },
            model=None,
            messages=[
                {
                    "role": "assistant",
                    "content": "Study answer",
                    "agent_id": "study",
                },
                {
                    "role": "assistant",
                    "content": "Legacy answer",
                },
            ],
        )

        payload = request.model_dump(
            mode="json"
        )

        self.assertEqual(
            payload["messages"][0]["agent_id"],
            "study",
        )
        self.assertIsNone(
            payload["messages"][1]["agent_id"]
        )

    def test_restore_inserts_agent_id_and_legacy_null(self):
        backup = {
            "chat": {
                "title": "Restored",
            },
            "model": {},
            "messages": [
                {
                    "role": "assistant",
                    "content": "Study answer",
                    "agent_id": "study",
                    "sources": [],
                },
                {
                    "role": "assistant",
                    "content": "Legacy answer",
                    "sources": [],
                },
            ],
        }

        cursor = mock.Mock()
        cursor.lastrowid = 77

        connection = mock.Mock()
        connection.cursor.return_value = cursor

        with mock.patch.object(
            history_service,
            "get_runtime_connection",
            return_value=connection,
        ):
            result = (
                history_service
                .restore_chat_backup(
                    backup
                )
            )

        insert_calls = [
            call
            for call in cursor.execute.call_args_list
            if (
                len(call.args) >= 2
                and "INSERT INTO messages"
                in call.args[0]
            )
        ]

        self.assertEqual(
            len(insert_calls),
            2,
        )

        first_sql = insert_calls[0].args[0]
        first_values = insert_calls[0].args[1]
        second_values = insert_calls[1].args[1]

        self.assertIn(
            "agent_id",
            first_sql,
        )

        self.assertEqual(
            first_values[6],
            "study",
        )
        self.assertIsNone(
            second_values[6]
        )

        self.assertEqual(
            result["chat_id"],
            77,
        )
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
