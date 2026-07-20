import tempfile
import unittest
from pathlib import Path

from app.config.rag import (
    load_rag_settings,
)
from app.services.rag_service import (
    RAGService,
    RAGServiceError,
)


POSTGRES_URL = (
    "postgresql://"
    "user:secret@"
    "db.example.com:5432/onkar"
)


class FakeEmbeddingFunction:
    def __call__(
        self,
        texts,
    ):
        return [
            (
                float(len(text)),
                0.25,
                0.75,
            )
            for text in texts
        ]

    def name(self):
        return "fake"


class WrongDimensionEmbedding:
    def __call__(
        self,
        texts,
    ):
        return [
            (0.1, 0.2)
            for _ in texts
        ]


class FakePgVectorStore:
    def __init__(self):
        self.replaced = []
        self.search_calls = []
        self.document_count = 1
        self.search_rows = [
            {
                "content": (
                    "Relevant durable "
                    "content"
                ),
                "filename": (
                    "Report.pdf"
                ),
                "page": 2,
                "document_id": (
                    "doc-1"
                ),
                "chunk_index": 0,
                "distance": 0.05,
            }
        ]
        self.deleted_filename = 4
        self.deleted_chat = 6

    def replace_document_chunks(
        self,
        chunks,
        *,
        chat_id,
        document_id,
    ):
        chunk_list = list(
            chunks
        )

        self.replaced.append(
            {
                "chunks": chunk_list,
                "chat_id": chat_id,
                "document_id": (
                    document_id
                ),
            }
        )

        return len(
            chunk_list
        )

    def count(
        self,
        *,
        chat_id,
    ):
        del chat_id

        return self.document_count

    def search(
        self,
        embedding,
        **kwargs,
    ):
        self.search_calls.append(
            {
                "embedding": tuple(
                    embedding
                ),
                **kwargs,
            }
        )

        return list(
            self.search_rows
        )

    def delete_filename(
        self,
        *,
        chat_id,
        filename,
    ):
        self.deleted_filename_call = (
            chat_id,
            filename,
        )

        return self.deleted_filename

    def delete_chat(
        self,
        *,
        chat_id,
    ):
        self.deleted_chat_call = (
            chat_id
        )

        return self.deleted_chat


class FakeCollection:
    def __init__(self):
        self.upserts = []
        self.deleted_ids = []
        self.query_result = {
            "documents": [
                [
                    "Local relevant content"
                ]
            ],
            "metadatas": [
                [
                    {
                        "filename": (
                            "Local.pdf"
                        ),
                        "page": 3,
                        "document_id": (
                            "local-doc"
                        ),
                        "chunk_index": 0,
                    }
                ]
            ],
            "distances": [
                [0.1]
            ],
        }
        self.ids = [
            "local-chunk"
        ]

    def upsert(
        self,
        **kwargs,
    ):
        self.upserts.append(
            kwargs
        )

    def count(self):
        return len(
            self.ids
        )

    def get(
        self,
        *,
        where,
    ):
        del where

        return {
            "ids": list(
                self.ids
            )
        }

    def query(self, **kwargs):
        self.query_kwargs = kwargs

        return self.query_result

    def delete(
        self,
        *,
        ids,
    ):
        self.deleted_ids.extend(
            ids
        )

        self.ids = []


class FakeChromaClient:
    def __init__(
        self,
        collection,
    ):
        self.collection = collection
        self.calls = []

    def get_or_create_collection(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.collection


def pgvector_settings():
    return load_rag_settings(
        {
            "DATABASE_URL": (
                POSTGRES_URL
            ),
            "RAG_BACKEND": (
                "pgvector"
            ),
            "RAG_EMBEDDING_DIMENSION": (
                "3"
            ),
        }
    )


def chroma_settings(
    path,
):
    return load_rag_settings(
        {
            "RAG_BACKEND": (
                "chroma"
            ),
            "RAG_EMBEDDING_DIMENSION": (
                "3"
            ),
            "VECTOR_DB_DIR": str(
                path
            ),
        }
    )


class RAGServiceBackendTests(
    unittest.TestCase
):
    def test_pgvector_initialization_does_not_create_chroma_client(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        self.assertEqual(
            service.backend,
            "pgvector",
        )

        self.assertIsNone(
            service.client
        )

        self.assertIsNone(
            service.collection
        )

        self.assertIs(
            service.store,
            store,
        )

    def test_pgvector_add_pdf_embeds_and_replaces_document_chunks(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        service.read_pdf = (
            lambda file_path: [
                {
                    "page": 1,
                    "text": (
                        "First durable page"
                    ),
                },
                {
                    "page": 2,
                    "text": (
                        "Second durable page"
                    ),
                },
            ]
        )

        result = service.add_pdf(
            "Report.pdf",
            chat_id=7,
            document_id="doc-1",
        )

        self.assertEqual(
            result["chunks"],
            2,
        )

        replacement = (
            store.replaced[0]
        )

        self.assertEqual(
            replacement["chat_id"],
            7,
        )

        self.assertEqual(
            replacement[
                "document_id"
            ],
            "doc-1",
        )

        chunks = replacement[
            "chunks"
        ]

        self.assertEqual(
            len(chunks),
            2,
        )

        self.assertEqual(
            chunks[0].filename,
            "Report.pdf",
        )

        self.assertEqual(
            len(
                chunks[0].embedding
            ),
            3,
        )

    def test_pgvector_search_preserves_existing_context_contract(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        result = service.search(
            query="durable question",
            chat_id=7,
            filename="Report.pdf",
        )

        self.assertIn(
            "Relevant durable content",
            result["context"],
        )

        self.assertEqual(
            result["sources"],
            [
                {
                    "type": "pdf",
                    "title": "Report.pdf",
                    "filename": (
                        "Report.pdf"
                    ),
                    "page": 2,
                    "chat_id": 7,
                }
            ],
        )

        self.assertEqual(
            len(
                store.search_calls[0]
                ["embedding"]
            ),
            3,
        )

    def test_pgvector_empty_filename_selection_does_not_search(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        result = service.search(
            query="question",
            chat_id=7,
            filenames=[],
        )

        self.assertEqual(
            result,
            {
                "context": "",
                "sources": [],
            },
        )

        self.assertEqual(
            store.search_calls,
            [],
        )

    def test_pgvector_delete_methods_preserve_response_contracts(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        pdf_result = (
            service.delete_pdf(
                "Report.pdf",
                chat_id=7,
            )
        )

        chat_result = (
            service.delete_chat(
                chat_id=7
            )
        )

        self.assertEqual(
            pdf_result[
                "deleted_chunks"
            ],
            4,
        )

        self.assertEqual(
            pdf_result[
                "remaining_chunks"
            ],
            0,
        )

        self.assertEqual(
            chat_result[
                "deleted_chunks"
            ],
            6,
        )

    def test_chroma_backend_preserves_index_and_search_behavior(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            collection = (
                FakeCollection()
            )

            client = FakeChromaClient(
                collection
            )

            service = RAGService(
                settings=(
                    chroma_settings(
                        Path(directory)
                    )
                ),
                embedding_function=(
                    FakeEmbeddingFunction()
                ),
                chroma_client=client,
            )

            service.read_pdf = (
                lambda file_path: [
                    {
                        "page": 1,
                        "text": (
                            "Local PDF text"
                        ),
                    }
                ]
            )

            indexed = service.add_pdf(
                "Local.pdf",
                chat_id=3,
                document_id=(
                    "local-doc"
                ),
            )

            searched = service.search(
                query="local question",
                chat_id=3,
            )

        self.assertEqual(
            service.backend,
            "chroma",
        )

        self.assertEqual(
            indexed["chunks"],
            1,
        )

        self.assertEqual(
            len(
                collection.upserts
            ),
            1,
        )

        self.assertIn(
            "Local relevant content",
            searched["context"],
        )

        self.assertEqual(
            searched["sources"][0]
            ["chat_id"],
            3,
        )

    def test_invalid_embedding_dimension_fails_before_database_write(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                WrongDimensionEmbedding()
            ),
            pgvector_store=store,
        )

        service.read_pdf = (
            lambda file_path: [
                {
                    "page": 1,
                    "text": "Content",
                }
            ]
        )

        with self.assertRaises(
            RAGServiceError
        ):
            service.add_pdf(
                "Report.pdf",
                chat_id=7,
                document_id="doc-1",
            )

        self.assertEqual(
            store.replaced,
            [],
        )

    def test_missing_query_or_chat_never_reaches_backend(
        self,
    ):
        store = FakePgVectorStore()

        service = RAGService(
            settings=(
                pgvector_settings()
            ),
            embedding_function=(
                FakeEmbeddingFunction()
            ),
            pgvector_store=store,
        )

        self.assertEqual(
            service.search(
                query="",
                chat_id=7,
            ),
            {
                "context": "",
                "sources": [],
            },
        )

        self.assertEqual(
            service.search(
                query="question",
                chat_id=None,
            ),
            {
                "context": "",
                "sources": [],
            },
        )

        self.assertEqual(
            store.search_calls,
            [],
        )


if __name__ == "__main__":
    unittest.main()
