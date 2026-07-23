from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.agents import brain as brain_module


class KnowledgeChatIntegrationTests(
    unittest.TestCase
):
    def make_brain(
        self,
        *,
        route="chat",
    ):
        brain = brain_module.Brain.__new__(
            brain_module.Brain
        )
        brain.rag = Mock()
        brain.ai = Mock()
        brain.internet = Mock()
        brain.router = Mock()
        brain.router.route.return_value = route
        return brain

    def knowledge_result(self):
        return {
            "context": (
                "Reusable policy context."
            ),
            "sources": [
                {
                    "type": "pdf",
                    "title": "Policy.pdf",
                    "filename": "Policy.pdf",
                    "page": 4,
                    "knowledge_id": (
                        "knowledge-1"
                    ),
                }
            ],
        }

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_chat_route_uses_grounded_knowledge_prompt(
        self,
        retrieve,
    ):
        retrieve.return_value = (
            self.knowledge_result()
        )
        brain = self.make_brain()

        prepared = brain.prepare_request(
            "What is the policy?",
            chat_id=27,
        )

        retrieve.assert_called_once_with(
            "What is the policy?",
            limit=5,
        )
        self.assertEqual(
            prepared["route"],
            "knowledge",
        )
        self.assertIn(
            "Reusable Knowledge Library Context:",
            prepared["prompt"],
        )
        self.assertIn(
            "Reusable policy context.",
            prepared["prompt"],
        )
        self.assertIn(
            "What is the policy?",
            prepared["prompt"],
        )
        self.assertLess(
            prepared["prompt"].index(
                "Reusable policy context."
            ),
            prepared["prompt"].index(
                "What is the policy?"
            ),
        )
        self.assertEqual(
            prepared["sources"],
            self.knowledge_result()[
                "sources"
            ],
        )

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_empty_knowledge_is_chat_no_op(
        self,
        retrieve,
    ):
        retrieve.return_value = {
            "context": "",
            "sources": [],
        }
        brain = self.make_brain()

        prepared = brain.prepare_request(
            "Hello",
            chat_id=9,
        )

        retrieve.assert_called_once_with(
            "Hello",
            limit=5,
        )
        self.assertEqual(
            prepared,
            {
                "route": "chat",
                "prompt": "Hello",
                "sources": [],
            },
        )

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_knowledge_failure_propagates(
        self,
        retrieve,
    ):
        retrieve.side_effect = RuntimeError(
            "temporary retrieval failure"
        )
        brain = self.make_brain()

        with self.assertRaisesRegex(
            RuntimeError,
            "temporary retrieval failure",
        ):
            brain.prepare_request(
                "Question",
                chat_id=3,
            )

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_internet_route_remains_unchanged(
        self,
        retrieve,
    ):
        brain = self.make_brain(
            route="internet"
        )
        brain.internet.search.return_value = {
            "answer": "Current answer",
            "sources": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                }
            ],
        }

        prepared = brain.prepare_request(
            "Search this",
            chat_id=5,
        )

        retrieve.assert_not_called()
        brain.rag.search.assert_not_called()
        self.assertEqual(
            prepared["route"],
            "internet",
        )
        self.assertIn(
            "Current answer",
            prepared["prompt"],
        )
        self.assertEqual(
            prepared["sources"],
            brain.internet.search.return_value[
                "sources"
            ],
        )

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    @patch(
        "app.agents.brain."
        "get_selected_document_filenames"
    )
    def test_pdf_route_remains_unchanged(
        self,
        selected_filenames,
        retrieve,
    ):
        selected_filenames.return_value = [
            "Selected.pdf"
        ]
        brain = self.make_brain(
            route="pdf"
        )
        brain.rag.search.return_value = {
            "context": "Selected PDF context.",
            "sources": [
                {
                    "type": "pdf",
                    "title": "Selected.pdf",
                    "filename": "Selected.pdf",
                    "page": 2,
                }
            ],
        }

        prepared = brain.prepare_request(
            "PDF question",
            chat_id=12,
        )

        retrieve.assert_not_called()
        selected_filenames.assert_called_once_with(
            12
        )
        brain.rag.search.assert_called_once_with(
            query="PDF question",
            chat_id=12,
            filenames=[
                "Selected.pdf"
            ],
        )
        self.assertEqual(
            prepared["route"],
            "pdf",
        )
        self.assertIn(
            "Selected PDF context.",
            prepared["prompt"],
        )

    @patch(
        "app.agents.brain.add"
    )
    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_chat_generation_uses_knowledge_prompt(
        self,
        retrieve,
        memory_add,
    ):
        retrieve.return_value = (
            self.knowledge_result()
        )
        brain = self.make_brain()
        brain.ai.generate_reply.return_value = (
            "Grounded reply"
        )
        brain.ai.resolve_model.return_value = (
            "model-1"
        )

        result = brain.chat(
            "What is the policy?",
            chat_id=15,
            model_id="model-1",
        )

        generated_prompt = (
            brain.ai.generate_reply
            .call_args.args[0]
        )
        self.assertIn(
            "Reusable policy context.",
            generated_prompt,
        )
        self.assertNotEqual(
            generated_prompt,
            "What is the policy?",
        )
        brain.ai.generate_reply.assert_called_once_with(
            generated_prompt,
            model_id="model-1",
        )
        self.assertEqual(
            result["reply"],
            "Grounded reply",
        )
        self.assertEqual(
            result["sources"],
            self.knowledge_result()[
                "sources"
            ],
        )
        self.assertEqual(
            result["model_id"],
            "model-1",
        )
        self.assertEqual(
            memory_add.call_count,
            2,
        )

    @patch(
        "app.agents.brain."
        "retrieve_knowledge_context"
    )
    def test_stream_generation_uses_knowledge_prompt(
        self,
        retrieve,
    ):
        retrieve.return_value = (
            self.knowledge_result()
        )
        brain = self.make_brain()
        stream = iter(
            [
                "Grounded ",
                "stream",
            ]
        )
        brain.ai.generate_reply_stream.return_value = (
            stream
        )
        brain.ai.resolve_model.return_value = (
            "model-2"
        )

        result = brain.stream_chat(
            "What is the policy?",
            chat_id=16,
            model_id="model-2",
        )

        generated_prompt = (
            brain.ai.generate_reply_stream
            .call_args.args[0]
        )
        self.assertIn(
            "Reusable policy context.",
            generated_prompt,
        )
        brain.ai.generate_reply_stream.assert_called_once_with(
            generated_prompt,
            model_id="model-2",
        )
        self.assertIs(
            result["stream"],
            stream,
        )
        self.assertEqual(
            result["sources"],
            self.knowledge_result()[
                "sources"
            ],
        )
        self.assertEqual(
            result["model_id"],
            "model-2",
        )


if __name__ == "__main__":
    unittest.main()
