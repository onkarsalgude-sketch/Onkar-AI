from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.api import chat as chat_api
from app.models.chat import MessageRegenerateRequest


class AgentRetryRegenerateTests(unittest.TestCase):
    def _user_message(self):
        return {
            "id": 10,
            "role": "user",
            "content": "Explain matrices",
            "attachment": None,
            "agent_id": None,
        }

    def _run_regenerate(
        self,
        *,
        request_agent_id=None,
        history_agent_id=None,
        result_agent_id=None,
    ):
        original = self._user_message()

        history = [
            original,
            {
                "id": 11,
                "role": "assistant",
                "content": "Original answer",
                "attachment": None,
                "agent_id": history_agent_id,
            },
        ]

        result = {
            "reply": "Regenerated answer",
            "sources": [],
            "model_id": "model-r",
        }

        if result_agent_id is not None:
            result["agent_id"] = result_agent_id

        fake_brain = SimpleNamespace(
            chat=mock.Mock(return_value=result)
        )

        with (
            mock.patch.object(
                chat_api,
                "get_message",
                return_value=original,
            ),
            mock.patch.object(
                chat_api,
                "get_messages",
                return_value=history,
            ),
            mock.patch.object(
                chat_api,
                "edit_user_message",
                return_value={
                    "deleted_following_messages": 1,
                },
            ),
            mock.patch.object(
                chat_api,
                "brain",
                fake_brain,
            ),
            mock.patch.object(
                chat_api,
                "save_message",
            ) as save_message,
        ):
            response = (
                chat_api.regenerate_message_response(
                    7,
                    10,
                    MessageRegenerateRequest(
                        model_id="model-r",
                        agent_id=request_agent_id,
                    ),
                )
            )

        return (
            response,
            fake_brain.chat,
            save_message,
        )

    def test_regenerate_uses_persisted_original_agent(self):
        (
            response,
            brain_chat,
            save_message,
        ) = self._run_regenerate(
            history_agent_id="study",
            result_agent_id="study",
        )

        brain_chat.assert_called_once_with(
            "Explain matrices",
            chat_id=7,
            model_id="model-r",
            agent_id="study",
        )

        self.assertEqual(
            save_message.call_args.kwargs["agent_id"],
            "study",
        )
        self.assertEqual(
            response["agent_id"],
            "study",
        )

    def test_regenerate_request_agent_survives_deleted_history(self):
        original = self._user_message()

        fake_brain = SimpleNamespace(
            chat=mock.Mock(
                return_value={
                    "reply": "Edited answer",
                    "sources": [],
                    "model_id": "model-r",
                    "agent_id": "coding",
                }
            )
        )

        with (
            mock.patch.object(
                chat_api,
                "get_message",
                return_value=original,
            ),
            mock.patch.object(
                chat_api,
                "get_messages",
                return_value=[original],
            ),
            mock.patch.object(
                chat_api,
                "edit_user_message",
                return_value={
                    "deleted_following_messages": 0,
                },
            ),
            mock.patch.object(
                chat_api,
                "brain",
                fake_brain,
            ),
            mock.patch.object(
                chat_api,
                "save_message",
            ) as save_message,
        ):
            response = (
                chat_api.regenerate_message_response(
                    7,
                    10,
                    MessageRegenerateRequest(
                        model_id="model-r",
                        agent_id="coding",
                    ),
                )
            )

        fake_brain.chat.assert_called_once_with(
            "Explain matrices",
            chat_id=7,
            model_id="model-r",
            agent_id="coding",
        )
        self.assertEqual(
            save_message.call_args.kwargs["agent_id"],
            "coding",
        )
        self.assertEqual(
            response["agent_id"],
            "coding",
        )

    def test_legacy_regenerate_remains_agent_neutral(self):
        (
            response,
            brain_chat,
            save_message,
        ) = self._run_regenerate(
            history_agent_id=None,
            result_agent_id=None,
        )

        brain_chat.assert_called_once_with(
            "Explain matrices",
            chat_id=7,
            model_id="model-r",
            agent_id=None,
        )

        self.assertIsNone(
            save_message.call_args.kwargs["agent_id"]
        )
        self.assertIsNone(
            response["agent_id"]
        )

    def test_frontend_regenerate_agent_contract(self):
        use_chat = Path(
            "frontend/src/hooks/useChat.js"
        ).read_text(
            encoding="utf-8",
        )
        use_chats = Path(
            "frontend/src/hooks/useChats.js"
        ).read_text(
            encoding="utf-8",
        )
        chat_service = Path(
            "frontend/src/services/chatService.js"
        ).read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "agentId:\n"
            "        message.agent_id ??\n"
            "        message.agentId ??\n"
            "        null,",
            use_chats,
        )

        self.assertGreaterEqual(
            use_chats.count(
                "responseAgentIdForMessage("
            ),
            3,
        )

        self.assertIn(
            "payload.agent_id = agentId;",
            chat_service,
        )

        self.assertIn(
            "const originalAgentId = normalizeAgentId(",
            use_chat,
        )
        self.assertIn(
            "agentId: originalAgentId,",
            use_chat,
        )
        self.assertIn(
            "originalAgentId\n"
            "        );",
            use_chat,
        )


if __name__ == "__main__":
    unittest.main()
