from __future__ import annotations

import math
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.utils.embedding_functions import (
    DefaultEmbeddingFunction,
)
from pypdf import PdfReader

from app.config.rag import (
    RAGSettings,
    load_rag_settings,
)
from app.config.settings import VECTOR_DB_DIR
from app.services.pgvector_rag_store import (
    PgVectorChunk,
    PgVectorRAGStore,
)


class RAGServiceError(RuntimeError):
    """Raised when RAG indexing or search cannot run safely."""

    def __init__(self):
        super().__init__(
            "RAG operation failed."
        )


class RAGService:
    def __init__(
        self,
        *,
        settings: RAGSettings
        | None = None,
        embedding_function=None,
        pgvector_store=None,
        chroma_client=None,
    ):
        self.settings = (
            settings
            if settings is not None
            else load_rag_settings(
                default_chroma_path=(
                    VECTOR_DB_DIR
                )
            )
        )

        self.embedding_function = (
            embedding_function
            if embedding_function
            is not None
            else DefaultEmbeddingFunction()
        )

        self.client = None
        self.collection = None
        self.store = None

        if self.settings.is_pgvector:
            self.store = (
                pgvector_store
                if pgvector_store
                is not None
                else PgVectorRAGStore(
                    self.settings
                )
            )

            return

        self.client = (
            chroma_client
            if chroma_client is not None
            else chromadb.PersistentClient(
                path=str(
                    self.settings
                    .chroma_path
                )
            )
        )

        self.collection = (
            self.client
            .get_or_create_collection(
                name=(
                    self.settings
                    .collection_name
                ),
                metadata={
                    "hnsw:space": "cosine"
                },
                embedding_function=(
                    self.embedding_function
                ),
            )
        )

    @property
    def backend(self) -> str:
        return self.settings.backend

    def _embed_texts(
        self,
        texts: list[str],
    ) -> list[tuple[float, ...]]:
        if not texts:
            return []

        try:
            raw_embeddings = (
                self.embedding_function(
                    list(texts)
                )
            )

            embeddings = [
                tuple(
                    float(value)
                    for value in vector
                )
                for vector
                in raw_embeddings
            ]
        except Exception as error:
            raise RAGServiceError() from error

        if len(embeddings) != len(texts):
            raise RAGServiceError()

        expected_dimension = (
            self.settings
            .embedding_dimension
        )

        for embedding in embeddings:
            if (
                len(embedding)
                != expected_dimension
                or not all(
                    math.isfinite(value)
                    for value in embedding
                )
            ):
                raise RAGServiceError()

        return embeddings

    def read_pdf(
        self,
        file_path: str | Path,
    ) -> list[dict]:
        reader = PdfReader(
            str(file_path)
        )

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = page.extract_text()

            if (
                page_text
                and page_text.strip()
            ):
                pages.append(
                    {
                        "page": page_number,
                        "text": (
                            page_text.strip()
                        ),
                    }
                )

        return pages

    def split_text(
        self,
        text: str,
        chunk_size: int = 900,
        overlap: int = 150,
    ) -> list[str]:
        text = " ".join(
            text.split()
        )

        if not text:
            return []

        if (
            chunk_size <= 0
            or overlap < 0
            or overlap >= chunk_size
        ):
            raise ValueError(
                "Invalid chunk configuration"
            )

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            chunk = text[
                start:end
            ].strip()

            if chunk:
                chunks.append(
                    chunk
                )

            if end >= len(text):
                break

            start = end - overlap

        return chunks

    def _prepare_chunks(
        self,
        *,
        pages: list[dict],
        chat_id: int,
        document_id: str,
        filename: str,
    ) -> tuple[
        list[str],
        list[str],
        list[dict],
    ]:
        all_chunks = []
        all_ids = []
        all_metadatas = []

        for page_data in pages:
            page_number = int(
                page_data["page"]
            )

            page_chunks = self.split_text(
                str(page_data["text"])
            )

            for (
                chunk_index,
                chunk,
            ) in enumerate(
                page_chunks
            ):
                all_chunks.append(
                    chunk
                )

                all_ids.append(
                    f"chat-{chat_id}-"
                    f"{document_id}-"
                    f"page-{page_number}-"
                    f"chunk-{chunk_index}"
                )

                all_metadatas.append(
                    {
                        "document_id": (
                            document_id
                        ),
                        "chat_id": chat_id,
                        "filename": filename,
                        "page": page_number,
                        "chunk_index": (
                            chunk_index
                        ),
                    }
                )

        return (
            all_chunks,
            all_ids,
            all_metadatas,
        )

    def add_pdf(
        self,
        file_path: str | Path,
        chat_id: int,
        document_id: str | None = None,
    ) -> dict:
        if chat_id <= 0:
            raise ValueError(
                "Invalid chat ID"
            )

        resolved_path = Path(
            file_path
        )

        pages = self.read_pdf(
            resolved_path
        )

        if not pages:
            return {
                "message": (
                    "No readable text "
                    "found in PDF"
                ),
                "filename": (
                    resolved_path.name
                ),
                "chat_id": chat_id,
                "pages": 0,
                "chunks": 0,
            }

        resolved_document_id = (
            document_id
            or uuid4().hex
        )

        (
            all_chunks,
            all_ids,
            all_metadatas,
        ) = self._prepare_chunks(
            pages=pages,
            chat_id=chat_id,
            document_id=(
                resolved_document_id
            ),
            filename=resolved_path.name,
        )

        if not all_chunks:
            return {
                "message": (
                    "No readable text "
                    "found in PDF"
                ),
                "filename": (
                    resolved_path.name
                ),
                "chat_id": chat_id,
                "pages": len(pages),
                "chunks": 0,
            }

        if self.settings.is_pgvector:
            embeddings = self._embed_texts(
                all_chunks
            )

            pgvector_chunks = [
                PgVectorChunk(
                    chunk_id=chunk_id,
                    chat_id=chat_id,
                    document_id=(
                        resolved_document_id
                    ),
                    filename=(
                        metadata[
                            "filename"
                        ]
                    ),
                    page=int(
                        metadata["page"]
                    ),
                    chunk_index=int(
                        metadata[
                            "chunk_index"
                        ]
                    ),
                    content=content,
                    embedding=embedding,
                )
                for (
                    chunk_id,
                    content,
                    metadata,
                    embedding,
                ) in zip(
                    all_ids,
                    all_chunks,
                    all_metadatas,
                    embeddings,
                    strict=True,
                )
            ]

            inserted_count = (
                self.store
                .replace_document_chunks(
                    pgvector_chunks,
                    chat_id=chat_id,
                    document_id=(
                        resolved_document_id
                    ),
                )
            )

        else:
            self.collection.upsert(
                ids=all_ids,
                documents=all_chunks,
                metadatas=(
                    all_metadatas
                ),
            )

            inserted_count = len(
                all_chunks
            )

        return {
            "message": (
                "PDF indexed successfully"
            ),
            "filename": (
                resolved_path.name
            ),
            "chat_id": chat_id,
            "pages": len(pages),
            "chunks": inserted_count,
        }

    def _build_where_filter(
        self,
        chat_id: int,
        filename: str | None = None,
        filenames:
        list[str] | None = None,
    ) -> dict:
        if filename:
            safe_filename = Path(
                filename
            ).name

            return {
                "$and": [
                    {
                        "chat_id": {
                            "$eq": chat_id
                        }
                    },
                    {
                        "filename": {
                            "$eq": (
                                safe_filename
                            )
                        }
                    },
                ]
            }

        if filenames is not None:
            safe_filenames = [
                Path(item).name
                for item in filenames
                if item
            ]

            if not safe_filenames:
                return {
                    "$and": [
                        {
                            "chat_id": {
                                "$eq": (
                                    chat_id
                                )
                            }
                        },
                        {
                            "filename": {
                                "$in": [
                                    "__no_pdf__"
                                ]
                            }
                        },
                    ]
                }

            return {
                "$and": [
                    {
                        "chat_id": {
                            "$eq": chat_id
                        }
                    },
                    {
                        "filename": {
                            "$in": (
                                safe_filenames
                            )
                        }
                    },
                ]
            }

        return {
            "chat_id": {
                "$eq": chat_id
            }
        }

    @staticmethod
    def _empty_search() -> dict:
        return {
            "context": "",
            "sources": [],
        }

    def _format_rows(
        self,
        rows: list[dict],
        *,
        chat_id: int,
    ) -> dict:
        if not rows:
            return self._empty_search()

        context_parts = []
        sources = []
        added_sources = set()

        for row in rows:
            document = str(
                row.get(
                    "content",
                    "",
                )
            )

            source_filename = (
                row.get(
                    "filename",
                    "Unknown PDF",
                )
            )

            page = row.get(
                "page",
                "Unknown",
            )

            context_parts.append(
                f"Source: "
                f"{source_filename}, "
                f"Page: {page}\n"
                f"Content:\n"
                f"{document}"
            )

            source_key = (
                f"{source_filename}:"
                f"{page}"
            )

            if (
                source_key
                not in added_sources
            ):
                added_sources.add(
                    source_key
                )

                sources.append(
                    {
                        "type": "pdf",
                        "title": (
                            source_filename
                        ),
                        "filename": (
                            source_filename
                        ),
                        "page": page,
                        "chat_id": chat_id,
                    }
                )

        return {
            "context": (
                "\n\n---\n\n".join(
                    context_parts
                )
            ),
            "sources": sources,
        }

    def search(
        self,
        query: str | None = None,
        limit: int = 5,
        chat_id: int | None = None,
        filename: str | None = None,
        filenames:
        list[str] | None = None,
    ) -> dict:
        if (
            not query
            or chat_id is None
            or chat_id <= 0
        ):
            return self._empty_search()

        if self.settings.is_pgvector:
            if (
                filenames is not None
                and not filenames
            ):
                return self._empty_search()

            if (
                self.store.count(
                    chat_id=chat_id
                )
                == 0
            ):
                return self._empty_search()

            query_embedding = (
                self._embed_texts(
                    [query]
                )[0]
            )

            rows = self.store.search(
                query_embedding,
                chat_id=chat_id,
                limit=limit,
                filename=filename,
                filenames=filenames,
            )

            return self._format_rows(
                rows,
                chat_id=chat_id,
            )

        if (
            self.collection.count()
            == 0
        ):
            return self._empty_search()

        where_filter = (
            self._build_where_filter(
                chat_id=chat_id,
                filename=filename,
                filenames=filenames,
            )
        )

        matching_records = (
            self.collection.get(
                where=where_filter
            )
        )

        matching_ids = (
            matching_records.get(
                "ids",
                [],
            )
        )

        if not matching_ids:
            return self._empty_search()

        results = self.collection.query(
            query_texts=[query],
            where=where_filter,
            n_results=min(
                limit,
                len(matching_ids),
            ),
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        documents = results.get(
            "documents",
            [],
        )

        metadatas = results.get(
            "metadatas",
            [],
        )

        if (
            not documents
            or not documents[0]
        ):
            return self._empty_search()

        rows = []

        for index, document in enumerate(
            documents[0]
        ):
            metadata = {}

            if (
                metadatas
                and metadatas[0]
            ):
                metadata = (
                    metadatas[0][index]
                    or {}
                )

            rows.append(
                {
                    "content": document,
                    "filename": (
                        metadata.get(
                            "filename",
                            "Unknown PDF",
                        )
                    ),
                    "page": metadata.get(
                        "page",
                        "Unknown",
                    ),
                    "document_id": (
                        metadata.get(
                            "document_id"
                        )
                    ),
                    "chunk_index": (
                        metadata.get(
                            "chunk_index"
                        )
                    ),
                }
            )

        return self._format_rows(
            rows,
            chat_id=chat_id,
        )

    def delete_pdf(
        self,
        filename: str,
        chat_id: int,
    ) -> dict:
        safe_filename = Path(
            filename
        ).name

        if self.settings.is_pgvector:
            deleted_count = (
                self.store
                .delete_filename(
                    chat_id=chat_id,
                    filename=(
                        safe_filename
                    ),
                )
            )

            return {
                "filename": (
                    safe_filename
                ),
                "chat_id": chat_id,
                "deleted_chunks": (
                    deleted_count
                ),
                "remaining_chunks": 0,
            }

        where_filter = (
            self._build_where_filter(
                chat_id=chat_id,
                filename=(
                    safe_filename
                ),
            )
        )

        existing_records = (
            self.collection.get(
                where=where_filter
            )
        )

        existing_ids = (
            existing_records.get(
                "ids",
                [],
            )
        )

        if existing_ids:
            self.collection.delete(
                ids=existing_ids
            )

        remaining_records = (
            self.collection.get(
                where=where_filter
            )
        )

        remaining_ids = (
            remaining_records.get(
                "ids",
                [],
            )
        )

        return {
            "filename": safe_filename,
            "chat_id": chat_id,
            "deleted_chunks": len(
                existing_ids
            ),
            "remaining_chunks": len(
                remaining_ids
            ),
        }

    def delete_chat(
        self,
        chat_id: int,
    ) -> dict:
        if self.settings.is_pgvector:
            deleted_count = (
                self.store.delete_chat(
                    chat_id=chat_id
                )
            )

            return {
                "chat_id": chat_id,
                "deleted_chunks": (
                    deleted_count
                ),
            }

        where_filter = {
            "chat_id": {
                "$eq": chat_id
            }
        }

        existing_records = (
            self.collection.get(
                where=where_filter
            )
        )

        existing_ids = (
            existing_records.get(
                "ids",
                [],
            )
        )

        if existing_ids:
            self.collection.delete(
                ids=existing_ids
            )

        return {
            "chat_id": chat_id,
            "deleted_chunks": len(
                existing_ids
            ),
        }

    def get_context(
        self,
        query: str | None = None,
        limit: int = 5,
        chat_id: int | None = None,
        filename: str | None = None,
    ) -> str:
        result = self.search(
            query=query,
            limit=limit,
            chat_id=chat_id,
            filename=filename,
        )

        return result["context"]
