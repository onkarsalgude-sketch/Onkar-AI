from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.services import (
    knowledge_retrieval_service,
)


class KnowledgeRetrievalServiceTests(
    unittest.TestCase
):
    def record(
        self,
        knowledge_id="knowledge-1",
    ):
        return {
            "knowledge_id": knowledge_id,
            "status": "ready",
            "is_enabled": True,
        }

    def test_invalid_request_stops_before_metadata(
        self,
    ):
        metadata_reader = Mock()

        invalid_requests = (
            {
                "query": "",
                "limit": 5,
            },
            {
                "query": "x" * 20_001,
                "limit": 5,
            },
            {
                "query": "question",
                "limit": True,
            },
            {
                "query": "question",
                "limit": 0,
            },
            {
                "query": "question",
                "limit": (
                        knowledge_retrieval_service
                        .MAX_KNOWLEDGE_SEARCH_LIMIT
                        + 1
                    ),
            },
        )

        for request in invalid_requests:
            with self.subTest(
                request=request
            ):
                with self.assertRaises(
                    knowledge_retrieval_service
                    .KnowledgeRetrievalValidationError
                ):
                    (
                        knowledge_retrieval_service
                        .retrieve_knowledge_context(
                            request["query"],
                            limit=request[
                                "limit"
                            ],
                            metadata_reader=(
                                metadata_reader
                            ),
                        )
                    )

        metadata_reader.assert_not_called()

    def test_metadata_selection_is_bounded_and_empty_safe(
        self,
    ):
        metadata_reader = Mock(
            return_value=[]
        )
        rag_factory = Mock()
        connection_factory = Mock()

        result = (
            knowledge_retrieval_service
            .retrieve_knowledge_context(
                "  durable question  ",
                limit=4,
                db_path="knowledge.db",
                connection_factory=(
                    connection_factory
                ),
                metadata_reader=(
                    metadata_reader
                ),
                rag_factory=rag_factory,
            )
        )

        self.assertEqual(
            result,
            {
                "context": "",
                "sources": [],
            },
        )
        metadata_reader.assert_called_once_with(
            limit=200,
            status="ready",
            enabled=True,
            db_path="knowledge.db",
            connection_factory=(
                connection_factory
            ),
        )
        rag_factory.assert_not_called()

    def test_success_uses_deduplicated_document_ids(
        self,
    ):
        metadata_reader = Mock(
            return_value=[
                self.record(
                    "knowledge-2"
                ),
                self.record(
                    "knowledge-1"
                ),
                self.record(
                    "knowledge-2"
                ),
            ]
        )
        rag = Mock()
        rag.search.return_value = {
            "context": (
                "Reusable context"
            ),
            "sources": [
                {
                    "type": "pdf",
                    "title": "Guide.pdf",
                    "filename": "Guide.pdf",
                    "page": 3,
                    "knowledge_id": (
                        "knowledge-2"
                    ),
                    "secret": (
                        "must-not-leak"
                    ),
                }
            ],
            "internal": "hidden",
        }
        rag_factory = Mock(
            return_value=rag
        )

        result = (
            knowledge_retrieval_service
            .retrieve_knowledge_context(
                "  durable question  ",
                limit=4,
                metadata_reader=(
                    metadata_reader
                ),
                rag_factory=rag_factory,
            )
        )

        rag.search.assert_called_once_with(
            "durable question",
            limit=4,
            document_ids=[
                "knowledge-2",
                "knowledge-1",
            ],
        )
        self.assertEqual(
            result,
            {
                "context": (
                    "Reusable context"
                ),
                "sources": [
                    {
                        "type": "pdf",
                        "title": "Guide.pdf",
                        "filename": "Guide.pdf",
                        "page": 3,
                        "knowledge_id": (
                            "knowledge-2"
                        ),
                    }
                ],
            },
        )
        self.assertNotIn(
            "must-not-leak",
            str(result),
        )
        self.assertNotIn(
            "hidden",
            str(result),
        )

    def test_malformed_metadata_stops_before_rag(
        self,
    ):
        malformed_values = (
            {},
            [
                "unsafe"
            ],
            [
                {
                    "knowledge_id": (
                        "knowledge-1"
                    ),
                    "status": "failed",
                    "is_enabled": True,
                }
            ],
            [
                {
                    "knowledge_id": (
                        "knowledge-1"
                    ),
                    "status": "ready",
                    "is_enabled": False,
                }
            ],
            [
                {
                    "knowledge_id": (
                        "../unsafe"
                    ),
                    "status": "ready",
                    "is_enabled": True,
                }
            ],
        )

        for value in malformed_values:
            with self.subTest(
                value=value
            ):
                rag_factory = Mock()

                with self.assertRaises(
                    knowledge_retrieval_service
                    .KnowledgeRetrievalError
                ):
                    (
                        knowledge_retrieval_service
                        .retrieve_knowledge_context(
                            "question",
                            metadata_reader=Mock(
                                return_value=(
                                    value
                                )
                            ),
                            rag_factory=(
                                rag_factory
                            ),
                        )
                    )

                rag_factory.assert_not_called()

    def test_metadata_failure_is_generic(
        self,
    ):
        secret = (
            "postgres://user:"
            "secret@private-host"
        )

        with self.assertRaises(
            knowledge_retrieval_service
            .KnowledgeRetrievalError
        ) as captured:
            (
                knowledge_retrieval_service
                .retrieve_knowledge_context(
                    "question",
                    metadata_reader=Mock(
                        side_effect=(
                            RuntimeError(
                                secret
                            )
                        )
                    ),
                )
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge retrieval failed.",
        )
        self.assertNotIn(
            secret,
            str(captured.exception),
        )

    def test_rag_factory_failure_is_generic(
        self,
    ):
        secret = (
            "vector://private-secret"
        )

        with self.assertRaises(
            knowledge_retrieval_service
            .KnowledgeRetrievalError
        ) as captured:
            (
                knowledge_retrieval_service
                .retrieve_knowledge_context(
                    "question",
                    metadata_reader=Mock(
                        return_value=[
                            self.record()
                        ]
                    ),
                    rag_factory=Mock(
                        side_effect=(
                            RuntimeError(
                                secret
                            )
                        )
                    ),
                )
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge retrieval failed.",
        )
        self.assertNotIn(
            secret,
            str(captured.exception),
        )

    def test_rag_search_failure_is_generic(
        self,
    ):
        secret = "embedding-api-key"
        rag = Mock()
        rag.search.side_effect = (
            RuntimeError(secret)
        )

        with self.assertRaises(
            knowledge_retrieval_service
            .KnowledgeRetrievalError
        ) as captured:
            (
                knowledge_retrieval_service
                .retrieve_knowledge_context(
                    "question",
                    metadata_reader=Mock(
                        return_value=[
                            self.record()
                        ]
                    ),
                    rag_factory=Mock(
                        return_value=rag
                    ),
                )
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge retrieval failed.",
        )
        self.assertNotIn(
            secret,
            str(captured.exception),
        )

    def test_invalid_rag_results_are_rejected(
        self,
    ):
        invalid_results = (
            None,
            {
                "context": 7,
                "sources": [],
            },
            {
                "context": "context",
                "sources": [
                    {
                        "type": "pdf",
                        "title": (
                            "Guide.pdf"
                        ),
                        "filename": (
                            "Guide.pdf"
                        ),
                        "page": 1,
                        "knowledge_id": (
                            "other-knowledge"
                        ),
                    }
                ],
            },
            {
                "context": "context",
                "sources": [
                    {
                        "type": "text",
                        "title": (
                            "Guide.pdf"
                        ),
                        "filename": (
                            "Guide.pdf"
                        ),
                        "page": 1,
                        "knowledge_id": (
                            "knowledge-1"
                        ),
                    }
                ],
            },
        )

        for result in invalid_results:
            with self.subTest(
                result=result
            ):
                rag = Mock()
                rag.search.return_value = (
                    result
                )

                with self.assertRaises(
                    knowledge_retrieval_service
                    .KnowledgeRetrievalError
                ):
                    (
                        knowledge_retrieval_service
                        .retrieve_knowledge_context(
                            "question",
                            metadata_reader=Mock(
                                return_value=[
                                    self.record()
                                ]
                            ),
                            rag_factory=Mock(
                                return_value=(
                                    rag
                                )
                            ),
                        )
                    )


if __name__ == "__main__":
    unittest.main()
