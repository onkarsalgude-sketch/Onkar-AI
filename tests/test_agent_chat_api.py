from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest.mock import Mock, call, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.agents import registry
from app.agents.selection import (
    AgentSelectionError,
)
from app.api import chat as chat_api
from app.models.chat import (
    ChatRequest,
    ChatResponse,
    MessageRegenerateRequest,
)


async def _consume_stream(response):
    chunks = []

    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(
                chunk.decode("utf-8")
            )
        else:
            chunks.append(str(chunk))

    return "".join(chunks)


class AgentChatApiIntegrationTests(
    unittest.TestCase
):
    def setUp(self):
        self.brain_chat = patch.object(
            chat_api.brain,
            "chat",
        )
        self.brain_stream = patch.object(
            chat_api.brain,
            "stream_chat",
        )
        self.generate_title = patch.object(
            chat_api.brain.ai,
            "generate_title",
        )
        self.create_chat = patch.object(
            chat_api,
            "create_chat",
        )
        self.get_messages = patch.object(
            chat_api,
            "get_messages",
        )
        self.rename_chat = patch.object(
            chat_api,
            "rename_chat",
        )
        self.save_message = patch.object(
            chat_api,
            "save_message",
        )

        self.mock_brain_chat = (
            self.brain_chat.start()
        )
        self.mock_brain_stream = (
            self.brain_stream.start()
        )
        self.mock_generate_title = (
            self.generate_title.start()
        )
        self.mock_create_chat = (
            self.create_chat.start()
        )
        self.mock_get_messages = (
            self.get_messages.start()
        )
        self.mock_rename_chat = (
            self.rename_chat.start()
        )
        self.mock_save_message = (
            self.save_message.start()
        )

        self.addCleanup(
            patch.stopall
        )

    def test_chat_request_is_backward_compatible(
        self,
    ):
        request = ChatRequest(
            message="Hello",
            chat_id=7,
            model_id="model-a",
        )

        self.assertIsNone(
            request.agent_id
        )
        self.assertEqual(
            request.model_dump(),
            {
                "message": "Hello",
                "chat_id": 7,
                "model_id": "model-a",
                "agent_id": None,
            },
        )

    def test_chat_request_accepts_bounded_agent_id(
        self,
    ):
        request = ChatRequest(
            message="Explain arrays.",
            agent_id="study",
        )

        self.assertEqual(
            request.agent_id,
            "study",
        )

        boundary = ChatRequest(
            message="Boundary",
            agent_id=(
                "a"
                * registry
                .MAX_AGENT_ID_LENGTH
            ),
        )

        self.assertEqual(
            len(boundary.agent_id),
            registry.MAX_AGENT_ID_LENGTH,
        )

    def test_chat_request_rejects_oversized_agent_id(
        self,
    ):
        with self.assertRaises(
            ValidationError
        ):
            ChatRequest(
                message="Too long",
                agent_id=(
                    "a"
                    * (
                        registry
                        .MAX_AGENT_ID_LENGTH
                        + 1
                    )
                ),
            )

    def test_chat_response_omits_none_agent_metadata(
        self,
    ):
        response = ChatResponse(
            reply="Hello",
            sources=[],
        )

        self.assertEqual(
            response.model_dump(
                exclude_none=True
            ),
            {
                "reply": "Hello",
                "sources": [],
            },
        )

        route = next(
            item
            for item in chat_api.router.routes
            if getattr(
                item,
                "path",
                None,
            ) == "/chat"
            and "POST"
            in getattr(
                item,
                "methods",
                set(),
            )
        )

        self.assertTrue(
            route.response_model_exclude_none
        )

    def test_legacy_chat_contract_remains_unchanged(
        self,
    ):
        self.mock_get_messages.return_value = [
            {
                "id": 1,
            }
        ]
        self.mock_brain_chat.return_value = {
            "reply": "Legacy reply",
            "sources": [],
            "model_id": "model-a",
        }

        response = chat_api.chat(
            ChatRequest(
                message="Hello",
                chat_id=7,
                model_id="model-a",
            )
        )

        self.mock_brain_chat.assert_called_once_with(
            "Hello",
            chat_id=7,
            model_id="model-a",
        )
        self.assertEqual(
            response.reply,
            "Legacy reply",
        )
        self.assertIsNone(
            response.agent_id
        )
        self.assertEqual(
            self.mock_save_message.call_args_list,
            [
                call(
                    7,
                    "user",
                    "Hello",
                ),
                call(
                    7,
                    "assistant",
                    "Legacy reply",
                    sources=[],
                    model_id="model-a",
                    agent_id=None,
                ),
            ],
        )

    def test_explicit_chat_forwards_and_returns_agent_id(
        self,
    ):
        self.mock_get_messages.return_value = [
            {
                "id": 1,
            }
        ]
        self.mock_brain_chat.return_value = {
            "reply": "Study reply",
            "sources": [],
            "model_id": "model-b",
            "agent_id": "study",
        }

        response = chat_api.chat(
            ChatRequest(
                message="Explain arrays.",
                chat_id=8,
                model_id="model-b",
                agent_id="study",
            )
        )

        self.mock_brain_chat.assert_called_once_with(
            "Explain arrays.",
            chat_id=8,
            model_id="model-b",
            agent_id="study",
        )
        self.assertEqual(
            response.agent_id,
            "study",
        )
        self.assertEqual(
            response.model_dump(
                exclude_none=True
            )["agent_id"],
            "study",
        )
        self.assertEqual(
            self.mock_save_message.call_count,
            2,
        )

    def test_invalid_chat_agent_is_generic_and_unpersisted(
        self,
    ):
        self.mock_create_chat.return_value = 42
        self.mock_get_messages.return_value = []
        self.mock_brain_chat.side_effect = (
            AgentSelectionError(
                "Unable to select agent."
            )
        )

        with self.assertRaises(
            HTTPException
        ) as context:
            chat_api.chat(
                ChatRequest(
                    message="Hello",
                    agent_id="missing-agent",
                )
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )
        self.assertEqual(
            context.exception.detail,
            "Unable to select agent.",
        )
        self.mock_create_chat.assert_called_once_with(
            "New Chat"
        )
        self.mock_generate_title.assert_not_called()
        self.mock_rename_chat.assert_not_called()
        self.mock_save_message.assert_not_called()

    def test_legacy_stream_headers_remain_unchanged(
        self,
    ):
        self.mock_get_messages.return_value = [
            {
                "id": 1,
            }
        ]
        self.mock_brain_stream.return_value = {
            "stream": iter(
                (
                    "one",
                    "two",
                )
            ),
            "sources": [],
            "model_id": "model-c",
        }

        response = chat_api.chat_stream(
            ChatRequest(
                message="Hello stream",
                chat_id=9,
                model_id="model-c",
            )
        )

        self.mock_brain_stream.assert_called_once_with(
            "Hello stream",
            chat_id=9,
            model_id="model-c",
        )
        self.assertNotIn(
            "x-agent-id",
            response.headers,
        )
        self.assertEqual(
            response.headers["x-chat-id"],
            "9",
        )
        self.assertEqual(
            response.headers["x-model-id"],
            "model-c",
        )

        body = asyncio.run(
            _consume_stream(response)
        )

        self.assertEqual(
            body,
            "onetwo",
        )
        self.assertEqual(
            self.mock_save_message.call_count,
            2,
        )

    def test_explicit_stream_forwards_and_adds_header(
        self,
    ):
        self.mock_get_messages.return_value = [
            {
                "id": 1,
            }
        ]
        self.mock_brain_stream.return_value = {
            "stream": iter(
                (
                    "study ",
                    "stream",
                )
            ),
            "sources": [],
            "model_id": "model-d",
            "agent_id": "study",
        }

        response = chat_api.chat_stream(
            ChatRequest(
                message="Quiz me.",
                chat_id=10,
                model_id="model-d",
                agent_id="study",
            )
        )

        self.mock_brain_stream.assert_called_once_with(
            "Quiz me.",
            chat_id=10,
            model_id="model-d",
            agent_id="study",
        )
        self.assertEqual(
            response.headers["x-agent-id"],
            "study",
        )

        body = asyncio.run(
            _consume_stream(response)
        )

        self.assertEqual(
            body,
            "study stream",
        )
        self.assertEqual(
            self.mock_save_message.call_args_list[-1],
            call(
                10,
                "assistant",
                "study stream",
                sources=[],
                model_id="model-d",
                agent_id="study",
            ),
        )

    def test_invalid_stream_agent_is_generic_and_unpersisted(
        self,
    ):
        self.mock_create_chat.return_value = 43
        self.mock_get_messages.return_value = []
        self.mock_brain_stream.side_effect = (
            AgentSelectionError(
                "Unable to select agent."
            )
        )

        with self.assertRaises(
            HTTPException
        ) as context:
            chat_api.chat_stream(
                ChatRequest(
                    message="Hello stream",
                    agent_id="missing-agent",
                )
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )
        self.assertEqual(
            context.exception.detail,
            "Unable to select agent.",
        )
        self.mock_create_chat.assert_called_once_with(
            "New Chat"
        )
        self.mock_generate_title.assert_not_called()
        self.mock_rename_chat.assert_not_called()
        self.mock_save_message.assert_not_called()

    def test_explicit_new_chat_titles_after_brain_success(
        self,
    ):
        self.mock_create_chat.return_value = 44
        self.mock_get_messages.return_value = []
        self.mock_generate_title.return_value = (
            "Study title"
        )
        self.mock_brain_chat.return_value = {
            "reply": "Reply",
            "sources": [],
            "model_id": "model-e",
            "agent_id": "study",
        }

        response = chat_api.chat(
            ChatRequest(
                message="Explain matrices.",
                model_id="model-e",
                agent_id="study",
            )
        )

        self.mock_brain_chat.assert_called_once_with(
            "Explain matrices.",
            chat_id=44,
            model_id="model-e",
            agent_id="study",
        )
        self.mock_generate_title.assert_called_once_with(
            "Explain matrices.",
            model_id="model-e",
        )
        self.mock_rename_chat.assert_called_once_with(
            44,
            "Study title",
        )
        self.assertEqual(
            response.agent_id,
            "study",
        )

    def test_regeneration_contract_accepts_optional_agent_id(
        self,
    ):
        fields = getattr(
            MessageRegenerateRequest,
            "model_fields",
            {},
        )

        self.assertEqual(
            tuple(fields),
            (
                "model_id",
                "agent_id",
            ),
        )

        source = inspect.getsource(
            chat_api
            .regenerate_message_response
        )

        self.assertIn(
            "agent_id",
            source,
        )


if __name__ == "__main__":
    unittest.main()
