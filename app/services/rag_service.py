from pathlib import Path
from uuid import uuid4

import chromadb
from pypdf import PdfReader

from app.config.settings import VECTOR_DB_DIR


class RAGService:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(VECTOR_DB_DIR)
        )

        self.collection = self.client.get_or_create_collection(
            name="pdf_documents",
            metadata={"hnsw:space": "cosine"},
        )

    def read_pdf(
        self,
        file_path: str | Path,
    ) -> list[dict]:
        reader = PdfReader(str(file_path))
        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = page.extract_text()

            if page_text and page_text.strip():
                pages.append(
                    {
                        "page": page_number,
                        "text": page_text.strip(),
                    }
                )

        return pages

    def split_text(
        self,
        text: str,
        chunk_size: int = 900,
        overlap: int = 150,
    ) -> list[str]:
        text = " ".join(text.split())

        if not text:
            return []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            if end >= len(text):
                break

            start = end - overlap

        return chunks

    def add_pdf(
        self,
        file_path: str | Path,
        chat_id: int,
        document_id: str | None = None,
    ) -> dict:
        if chat_id <= 0:
            raise ValueError("Invalid chat ID")

        file_path = Path(file_path)
        pages = self.read_pdf(file_path)

        if not pages:
            return {
                "message": "No readable text found in PDF",
                "filename": file_path.name,
                "chat_id": chat_id,
                "pages": 0,
                "chunks": 0,
            }

        document_id = document_id or uuid4().hex

        all_chunks = []
        all_ids = []
        all_metadatas = []

        for page_data in pages:
            page_number = page_data["page"]

            page_chunks = self.split_text(
                page_data["text"]
            )

            for chunk_index, chunk in enumerate(
                page_chunks
            ):
                all_chunks.append(chunk)

                all_ids.append(
                    f"chat-{chat_id}-"
                    f"{document_id}-"
                    f"page-{page_number}-"
                    f"chunk-{chunk_index}"
                )

                all_metadatas.append(
                    {
                        "document_id": document_id,
                        "chat_id": chat_id,
                        "filename": file_path.name,
                        "page": page_number,
                        "chunk_index": chunk_index,
                    }
                )

        if not all_chunks:
            return {
                "message": "No readable text found in PDF",
                "filename": file_path.name,
                "chat_id": chat_id,
                "pages": len(pages),
                "chunks": 0,
            }

        self.collection.add(
            ids=all_ids,
            documents=all_chunks,
            metadatas=all_metadatas,
        )

        return {
            "message": "PDF indexed successfully",
            "filename": file_path.name,
            "chat_id": chat_id,
            "pages": len(pages),
            "chunks": len(all_chunks),
        }

    def _build_where_filter(
        self,
        chat_id: int,
        filename: str | None = None,
        filenames: list[str] | None = None,
    ) -> dict:
        if filename:
            safe_filename = Path(filename).name

            return {
                "$and": [
                    {
                        "chat_id": {
                            "$eq": chat_id,
                        }
                    },
                    {
                        "filename": {
                            "$eq": safe_filename,
                        }
                    },
                ]
            }

        if filenames:
            safe_filenames = [
                Path(item).name
                for item in filenames
                if item
            ]

            return {
                "$and": [
                    {
                        "chat_id": {
                            "$eq": chat_id,
                        }
                    },
                    {
                        "filename": {
                            "$in": safe_filenames,
                        }
                    },
                ]
            }

        return {
            "chat_id": {
                "$eq": chat_id,
            }
        }

    def search(
        self,
        query: str | None = None,
        limit: int = 5,
        chat_id: int | None = None,
        filename: str | None = None,
        filenames: list[str] | None = None,
    ) -> dict:
        # chat_id नसल्यास कोणत्याही PDF मधून
        # search करू नये. यामुळे cross-chat leak थांबतो.
        if (
            not query
            or chat_id is None
            or chat_id <= 0
            or self.collection.count() == 0
        ):
            return {
                "context": "",
                "sources": [],
            }

        where_filter = self._build_where_filter(
            chat_id=chat_id,
            filename=filename,
            filenames=filenames,
        )

        matching_records = self.collection.get(
            where=where_filter
        )

        matching_ids = matching_records.get(
            "ids",
            [],
        )

        if not matching_ids:
            return {
                "context": "",
                "sources": [],
            }

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

        if not documents or not documents[0]:
            return {
                "context": "",
                "sources": [],
            }

        context_parts = []
        sources = []
        added_sources = set()

        for index, document in enumerate(
            documents[0]
        ):
            metadata = {}

            if metadatas and metadatas[0]:
                metadata = (
                    metadatas[0][index] or {}
                )

            source_filename = metadata.get(
                "filename",
                "Unknown PDF",
            )

            page = metadata.get(
                "page",
                "Unknown",
            )

            context_parts.append(
                f"Source: {source_filename}, "
                f"Page: {page}\n"
                f"Content:\n{document}"
            )

            source_key = (
                f"{source_filename}:{page}"
            )

            if source_key not in added_sources:
                added_sources.add(source_key)

                sources.append(
                    {
                        "type": "pdf",
                        "title": source_filename,
                        "filename": source_filename,
                        "page": page,
                        "chat_id": chat_id,
                    }
                )

        return {
            "context": "\n\n---\n\n".join(
                context_parts
            ),
            "sources": sources,
        }

    def delete_pdf(
        self,
        filename: str,
        chat_id: int,
    ) -> dict:
        safe_filename = Path(filename).name

        where_filter = self._build_where_filter(
            chat_id=chat_id,
            filename=safe_filename,
        )

        existing_records = self.collection.get(
            where=where_filter
        )

        existing_ids = existing_records.get(
            "ids",
            [],
        )

        if existing_ids:
            self.collection.delete(
                ids=existing_ids
            )

        remaining_records = self.collection.get(
            where=where_filter
        )

        remaining_ids = remaining_records.get(
            "ids",
            [],
        )

        return {
            "filename": safe_filename,
            "chat_id": chat_id,
            "deleted_chunks": len(existing_ids),
            "remaining_chunks": len(
                remaining_ids
            ),
        }

    def delete_chat(
        self,
        chat_id: int,
    ) -> dict:
        where_filter = {
            "chat_id": {
                "$eq": chat_id,
            }
        }

        existing_records = self.collection.get(
            where=where_filter
        )

        existing_ids = existing_records.get(
            "ids",
            [],
        )

        if existing_ids:
            self.collection.delete(
                ids=existing_ids
            )

        return {
            "chat_id": chat_id,
            "deleted_chunks": len(existing_ids),
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