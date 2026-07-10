from pathlib import Path
from uuid import uuid4

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from app.config.settings import VECTOR_DB_DIR


class RAGService:
    def __init__(self):
        self.embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        self.client = chromadb.PersistentClient(
            path=str(VECTOR_DB_DIR)
        )

        self.collection = self.client.get_or_create_collection(
            name="pdf_documents",
            metadata={"hnsw:space": "cosine"},
        )

    def read_pdf(self, file_path: str | Path) -> str:
        reader = PdfReader(str(file_path))
        pages = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages.append(page_text.strip())

        return "\n".join(pages)

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
        text = self.read_pdf(file_path)
        chunks = self.split_text(text)

        if not chunks:
            return {
                "message": "No readable text found in PDF",
                "chunks": 0,
            }

        embeddings = self.embedding_model.encode(
            chunks,
            normalize_embeddings=True,
        ).tolist()

        document_id = uuid4().hex

        ids = [
            f"{document_id}-{index}"
            for index in range(len(chunks))
        ]

        metadatas = [
            {
                "filename": file_path.name,
                "chunk_index": index,
            }
            for index in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return {
            "message": "PDF indexed successfully",
            "filename": file_path.name,
            "chunks": len(chunks),
        }

    def get_context(
        self,
        query: str | None = None,
        limit: int = 5,
    ) -> str:
        if not query:
            return ""

        if self.collection.count() == 0:
            return ""

        query_embedding = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
        ).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(limit, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [])

        if not documents or not documents[0]:
            return ""

        return "\n\n".join(documents[0])