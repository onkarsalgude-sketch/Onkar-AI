from __future__ import annotations

import asyncio
import ast
import inspect
import textwrap
import unittest
from types import SimpleNamespace
from unittest import mock

from app.api import chat as chat_api


class AgentMessagePersistenceApiTests(unittest.TestCase):
    @staticmethod
    async def _read_stream(response) -> str:
        chunks = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8"))
            else:
                chunks.append(str(chunk))
        return "".join(chunks)

    @staticmethod
    def _assistant_call(save_mock):
        calls = [
            item for item in save_mock.call_args_list
            if len(item.args) >= 2 and item.args[1] == "assistant"
        ]
        if len(calls) != 1:
            raise AssertionError("Expected exactly one assistant persistence call.")
        return calls[0]

    @staticmethod
    def _user_call(save_mock):
        calls = [
            item for item in save_mock.call_args_list
            if len(item.args) >= 2 and item.args[1] == "user"
        ]
        if len(calls) != 1:
            raise AssertionError("Expected exactly one user persistence call.")
        return calls[0]

    def test_normal_explicit_agent_is_persisted(self):
        request = SimpleNamespace(
            message="Explain pointers",
            chat_id=41,
            model_id="model-a",
            agent_id="study",
        )
        fake_brain = SimpleNamespace(
            chat=mock.Mock(return_value={
                "reply": "Pointer answer",
                "sources": [],
                "model_id": "model-a",
                "agent_id": "study",
            }),
            ai=SimpleNamespace(generate_title=mock.Mock()),
        )
        with (
            mock.patch.object(chat_api, "brain", fake_brain),
            mock.patch.object(
                chat_api, "get_messages", return_value=[{"id": 1}]
            ),
            mock.patch.object(chat_api, "save_message") as save_message,
        ):
            response = chat_api.chat(request)

        self.assertEqual(response.agent_id, "study")
        user_call = self._user_call(save_message)
        assistant_call = self._assistant_call(save_message)
        self.assertNotIn("agent_id", user_call.kwargs)
        self.assertEqual(assistant_call.kwargs["agent_id"], "study")

    def test_normal_legacy_flow_persists_none_agent(self):
        request = SimpleNamespace(
            message="Hello",
            chat_id=42,
            model_id="model-a",
            agent_id=None,
        )
        fake_brain = SimpleNamespace(
            chat=mock.Mock(return_value={
                "reply": "Hello back",
                "sources": [],
                "model_id": "model-a",
            }),
            ai=SimpleNamespace(generate_title=mock.Mock()),
        )
        with (
            mock.patch.object(chat_api, "brain", fake_brain),
            mock.patch.object(
                chat_api, "get_messages", return_value=[{"id": 1}]
            ),
            mock.patch.object(chat_api, "save_message") as save_message,
        ):
            response = chat_api.chat(request)

        self.assertIsNone(response.agent_id)
        assistant_call = self._assistant_call(save_message)
        self.assertIsNone(assistant_call.kwargs["agent_id"])

    def test_stream_explicit_agent_is_persisted(self):
        request = SimpleNamespace(
            message="Explain arrays",
            chat_id=43,
            model_id="model-b",
            agent_id="coding",
        )
        fake_brain = SimpleNamespace(
            stream_chat=mock.Mock(return_value={
                "stream": iter(("Array ", "answer")),
                "sources": [],
                "model_id": "model-b",
                "agent_id": "coding",
            }),
            ai=SimpleNamespace(generate_title=mock.Mock()),
        )
        with (
            mock.patch.object(chat_api, "brain", fake_brain),
            mock.patch.object(
                chat_api, "get_messages", return_value=[{"id": 1}]
            ),
            mock.patch.object(chat_api, "save_message") as save_message,
        ):
            response = chat_api.chat_stream(request)
            body = asyncio.run(self._read_stream(response))

        self.assertEqual(body, "Array answer")
        self.assertEqual(response.headers.get("x-agent-id"), "coding")
        user_call = self._user_call(save_message)
        assistant_call = self._assistant_call(save_message)
        self.assertNotIn("agent_id", user_call.kwargs)
        self.assertEqual(assistant_call.kwargs["agent_id"], "coding")

    def test_stream_legacy_flow_persists_none_agent(self):
        request = SimpleNamespace(
            message="Legacy stream",
            chat_id=44,
            model_id="model-c",
            agent_id=None,
        )
        fake_brain = SimpleNamespace(
            stream_chat=mock.Mock(return_value={
                "stream": iter(("Legacy",)),
                "sources": [],
                "model_id": "model-c",
            }),
            ai=SimpleNamespace(generate_title=mock.Mock()),
        )
        with (
            mock.patch.object(chat_api, "brain", fake_brain),
            mock.patch.object(
                chat_api, "get_messages", return_value=[{"id": 1}]
            ),
            mock.patch.object(chat_api, "save_message") as save_message,
        ):
            response = chat_api.chat_stream(request)
            body = asyncio.run(self._read_stream(response))

        self.assertEqual(body, "Legacy")
        self.assertIsNone(response.headers.get("x-agent-id"))
        assistant_call = self._assistant_call(save_message)
        self.assertIsNone(assistant_call.kwargs["agent_id"])

    def test_regenerate_persistence_is_agent_aware(self):
        source = textwrap.dedent(
            inspect.getsource(chat_api.regenerate_message_response)
        )
        tree = ast.parse(source)
        save_calls = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "save_message"
            ):
                save_calls.append(node)

        self.assertEqual(len(save_calls), 1)
        keyword_names = {
            keyword.arg
            for keyword in save_calls[0].keywords
            if keyword.arg is not None
        }
        self.assertIn("agent_id", keyword_names)


if __name__ == "__main__":
    unittest.main()
