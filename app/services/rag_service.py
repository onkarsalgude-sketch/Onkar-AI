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

    def read_pdf(self, file_path: str | Path) -> list[dict]:
        reader = PdfReader(str(file_path))
        pages = []

        for page_number, page in enumerate(reader.pages, start=1):
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

    def add_pdf(self, file_path: str | Path) -> dict:
        file_path = Path(file_path)
        pages = self.read_pdf(file_path)

        if not pages:
            return {
                "message": "No readable text found in PDF",
                "filename": file_path.name,
                "pages": 0,
                "chunks": 0,
            }

        document_id = uuid4().hex

        all_chunks = []
        all_ids = []
        all_metadata = []

        for page_data in pages:
            page_number = page_data["page"]
            page_chunks = self.split_text(page_data["text"])

            for chunk_index, chunk in enumerate(page_chunks):
                all_chunks.append(chunk)

                all_ids.append(
                    f"{document_id}-page-{page_number}-chunk-{chunk_index}"
                )

                all_metadata.append(
                    {
                        "document_id": document_id,
                        "filename": file_path.name,
                        "page": page_number,
                        "chunk_index": chunk_index,
                    }
                )

        if not all_chunks:
            return {
                "message": "No readable text found in PDF",
                "filename": file_path.name,
                "pages": len(pages),
                "chunks": 0,
            }

       

        self.collection.add(
            ids=all_ids,
            documents=all_chunks,
            metadatas=all_metadata,
        )

        return {
            "message": "PDF indexed successfully",
            "filename": file_path.name,
            "pages": len(pages),
            "chunks": len(all_chunks),
        }

    def search(
        self,
        query: str | None = None,
        limit: int = 5,
    ) -> dict:
        if not query or self.collection.count() == 0:
            return {
                "context": "",
                "sources": [],
            }


        results = self.collection.query(
            query_texts=[query],
            n_results=min(limit, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])

        if not documents or not documents[0]:
            return {
                "context": "",
                "sources": [],
            }

        context_parts = []
        sources = []
        added_sources = set()

        for index, document in enumerate(documents[0]):
            metadata = {}

            if metadatas and metadatas[0]:
                metadata = metadatas[0][index] or {}

            filename = metadata.get("filename", "Unknown PDF")
            page = metadata.get("page", "Unknown")

            context_parts.append(
                f"Source: {filename}, Page: {page}\n"
                f"Content:\n{document}"
            )

            source_key = f"{filename}:{page}"

            if source_key not in added_sources:
                added_sources.add(source_key)

                sources.append(
                    {
                        "type": "pdf",
                        "title": filename,
                        "filename": filename,
                        "page": page,
                    }
                )

        return {
            "context": "\n\n---\n\n".join(context_parts),
            "sources": sources,
        }
    def delete_pdf(self, filename: str) -> dict:
        safe_filename = Path(filename).name

        results = self.collection.get(
            where={"filename": safe_filename}
        )

        chunk_ids = results.get("ids", [])

        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

        return {
            "filename": safe_filename,
            "deleted_chunks": len(chunk_ids),
        }

    def get_context(
        self,
        query: str | None = None,
        limit: int = 5,
    ) -> str:
        result = self.search(query, limit)
        return result["context"]