import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config.rag import load_rag_settings
from app.config.settings import VECTOR_DB_DIR
from app.services import knowledge_rag_service


class FakeRAGService:
    backend = "chroma"

    def __init__(self):
        self.index_calls = []
        self.search_calls = []
        self.delete_calls = []

    def add_pdf(
        self,
        *,
        file_path,
        chat_id,
        document_id,
    ):
        self.index_calls.append(
            {
                "file_path": file_path,
                "chat_id": chat_id,
                "document_id": document_id,
            }
        )
        return {
            "filename": Path(
                file_path
            ).name,
            "chat_id": chat_id,
            "pages": 3,
            "chunks": 7,
        }

    def search(
        self,
        *,
        query,
        limit,
        chat_id,
        filenames,
    ):
        self.search_calls.append(
            {
                "query": query,
                "limit": limit,
                "chat_id": chat_id,
                "filenames": filenames,
            }
        )
        return {
            "context": "Reusable context",
            "sources": [
                {
                    "type": "pdf",
                    "title": "Guide.pdf",
                    "filename": "Guide.pdf",
                    "page": 2,
                    "chat_id": chat_id,
                    "document_id": (
                        "knowledge-1"
                    ),
                }
            ],
        }

    def delete_document(
        self,
        *,
        document_id,
        filename,
        chat_id,
    ):
        self.delete_calls.append(
            {
                "document_id": (
                    document_id
                ),
                "filename": filename,
                "chat_id": chat_id,
            }
        )
        return {
            "document_id": document_id,
            "filename": filename,
            "chat_id": chat_id,
            "deleted_chunks": 7,
            "remaining_chunks": 0,
        }


def chroma_settings(path: Path):
    return load_rag_settings(
        {
            "RAG_BACKEND": "chroma",
            "RAG_EMBEDDING_DIMENSION": (
                "3"
            ),
            "RAG_COLLECTION_NAME": (
                "pdf_documents"
            ),
            "VECTOR_DB_DIR": str(path),
        }
    )


class KnowledgeRAGNamespaceTests(
    unittest.TestCase
):
    def test_constants_define_safe_namespace(
        self,
    ):
        self.assertEqual(
            knowledge_rag_service
            .KNOWLEDGE_COLLECTION_NAME,
            "knowledge_documents",
        )
        self.assertGreater(
            knowledge_rag_service
            .KNOWLEDGE_INTERNAL_SCOPE_ID,
            0,
        )
        self.assertNotEqual(
            knowledge_rag_service
            .KNOWLEDGE_COLLECTION_NAME,
            "pdf_documents",
        )

    def test_settings_clone_preserves_backend(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            base = chroma_settings(
                Path(directory)
            )
            result = (
                knowledge_rag_service
                .build_knowledge_rag_settings(
                    base_settings=base
                )
            )

        self.assertEqual(
            result.collection_name,
            "knowledge_documents",
        )
        self.assertEqual(
            result.backend,
            base.backend,
        )
        self.assertEqual(
            result.embedding_dimension,
            base.embedding_dimension,
        )
        self.assertEqual(
            result.chroma_path,
            base.chroma_path,
        )
        self.assertEqual(
            result.database,
            base.database,
        )
        self.assertEqual(
            base.collection_name,
            "pdf_documents",
        )

    def test_settings_loader_uses_global_path(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            base = chroma_settings(
                Path(directory)
            )
            loader = Mock(
                return_value=base
            )

            result = (
                knowledge_rag_service
                .build_knowledge_rag_settings(
                    settings_loader=loader
                )
            )

        loader.assert_called_once_with(
            default_chroma_path=(
                VECTOR_DB_DIR
            )
        )
        self.assertEqual(
            result.collection_name,
            "knowledge_documents",
        )

    def test_service_factory_injects_namespace(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            base = chroma_settings(
                Path(directory)
            )
            embedding = object()
            store = object()
            client = object()
            created = object()

            with patch.object(
                knowledge_rag_service,
                "RAGService",
                return_value=created,
            ) as constructor:
                result = (
                    knowledge_rag_service
                    .create_knowledge_rag_service(
                        settings=base,
                        embedding_function=(
                            embedding
                        ),
                        pgvector_store=store,
                        chroma_client=client,
                    )
                )

        self.assertIs(result, created)
        kwargs = (
            constructor.call_args.kwargs
        )
        self.assertEqual(
            kwargs["settings"]
            .collection_name,
            "knowledge_documents",
        )
        self.assertIs(
            kwargs["embedding_function"],
            embedding,
        )
        self.assertIs(
            kwargs["pgvector_store"],
            store,
        )
        self.assertIs(
            kwargs["chroma_client"],
            client,
        )

    def test_index_uses_internal_scope(
        self,
    ):
        backend = FakeRAGService()
        service = (
            knowledge_rag_service
            .KnowledgeRAGService(
                service=backend
            )
        )

        result = service.index_pdf(
            file_path="C:/temp/Guide.pdf",
            knowledge_id="knowledge-1",
        )

        self.assertEqual(
            result,
            {
                "knowledge_id": (
                    "knowledge-1"
                ),
                "filename": "Guide.pdf",
                "pages": 3,
                "chunks": 7,
            },
        )
        self.assertEqual(
            backend.index_calls,
            [
                {
                    "file_path": Path(
                        "C:/temp/Guide.pdf"
                    ),
                    "chat_id": 1,
                    "document_id": (
                        "knowledge-1"
                    ),
                }
            ],
        )

    def test_search_is_scoped_and_sanitized(
        self,
    ):
        backend = FakeRAGService()
        service = (
            knowledge_rag_service
            .KnowledgeRAGService(
                service=backend
            )
        )

        result = service.search(
            " durable question ",
            limit=4,
            filenames=[
                "../Guide.pdf",
                "Guide.pdf",
            ],
        )

        self.assertEqual(
            backend.search_calls,
            [
                {
                    "query": (
                        "durable question"
                    ),
                    "limit": 4,
                    "chat_id": 1,
                    "filenames": [
                        "Guide.pdf"
                    ],
                }
            ],
        )
        self.assertEqual(
            result["context"],
            "Reusable context",
        )
        self.assertEqual(
            result["sources"],
            [
                {
                    "type": "pdf",
                    "title": "Guide.pdf",
                    "filename": (
                        "Guide.pdf"
                    ),
                    "page": 2,
                    "knowledge_id": (
                        "knowledge-1"
                    ),
                }
            ],
        )
        self.assertNotIn(
            "chat_id",
            str(result),
        )

    def test_delete_uses_internal_scope(
        self,
    ):
        backend = FakeRAGService()
        service = (
            knowledge_rag_service
            .KnowledgeRAGService(
                service=backend
            )
        )

        result = service.delete_document(
            knowledge_id="knowledge-1",
            filename="../Guide.pdf",
        )

        self.assertEqual(
            backend.delete_calls,
            [
                {
                    "document_id": (
                        "knowledge-1"
                    ),
                    "filename": "Guide.pdf",
                    "chat_id": 1,
                }
            ],
        )
        self.assertEqual(
            result["deleted_chunks"],
            7,
        )
        self.assertEqual(
            result["remaining_chunks"],
            0,
        )
        self.assertNotIn(
            "chat_id",
            result,
        )

    def test_invalid_inputs_stop_before_backend(
        self,
    ):
        backend = Mock()
        service = (
            knowledge_rag_service
            .KnowledgeRAGService(
                service=backend
            )
        )

        operations = (
            lambda: service.index_pdf(
                file_path="report.txt",
                knowledge_id="knowledge-1",
            ),
            lambda: service.index_pdf(
                file_path="report.pdf",
                knowledge_id="../unsafe",
            ),
            lambda: service.search(""),
            lambda: service.search(
                "question",
                limit=0,
            ),
            lambda: service.search(
                "question",
                filenames=[],
            ),
            lambda: (
                service.delete_document(
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    filename="report.txt",
                )
            ),
        )

        for operation in operations:
            with self.subTest(
                operation=operation
            ):
                with self.assertRaises(
                    knowledge_rag_service
                    .KnowledgeRAGError
                ):
                    operation()

        backend.add_pdf.assert_not_called()
        backend.search.assert_not_called()
        backend.delete_document.assert_not_called()

    def test_backend_failure_is_sanitized(
        self,
    ):
        backend = Mock()
        backend.add_pdf.side_effect = (
            RuntimeError(
                "postgresql://user:secret@host/db"
            )
        )
        service = (
            knowledge_rag_service
            .KnowledgeRAGService(
                service=backend
            )
        )

        with self.assertRaises(
            knowledge_rag_service
            .KnowledgeRAGError
        ) as captured:
            service.index_pdf(
                file_path="report.pdf",
                knowledge_id="knowledge-1",
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge vector operation failed.",
        )
        self.assertNotIn(
            "secret",
            str(captured.exception),
        )

    def test_constructor_failure_is_sanitized(
        self,
    ):
        loader = Mock(
            side_effect=RuntimeError(
                "chroma:///private/vector/path"
            )
        )

        with self.assertRaises(
            knowledge_rag_service
            .KnowledgeRAGError
        ) as captured:
            (
                knowledge_rag_service
                .create_knowledge_rag_service(
                    settings_loader=loader
                )
            )

        self.assertEqual(
            str(captured.exception),
            "Knowledge vector operation failed.",
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )


if __name__ == "__main__":
    unittest.main()
