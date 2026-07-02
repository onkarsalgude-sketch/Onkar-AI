import os
from pypdf import PdfReader
import chromadb
from sentence_transformers import SentenceTransformer
import uuid


class RAGService:
    def __init__(self):
        self.upload_dir = "app/uploads"
        self.chroma = chromadb.PersistentClient(path="app/vector_db")
        self.collection = self.chroma.get_or_create_collection("documents")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def read_pdf(self, file_path: str) -> str:
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        return text

    def chunk_text(self, text: str, chunk_size: int = 800):
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    def add_pdf(self, file_path: str):
        text = self.read_pdf(file_path)
        chunks = self.chunk_text(text)

        for index, chunk in enumerate(chunks):
            embedding = self.embedder.encode(chunk).tolist()

            self.collection.add(
                ids=[f"{os.path.basename(file_path)}-{index}-{uuid.uuid4()}"],
                documents=[chunk],
                embeddings=[embedding],
                metadatas=[{"source": os.path.basename(file_path)}]
            )

        return {"message": "PDF added to knowledge base", "chunks": len(chunks)}

    def search(self, query: str, n_results: int = 3):
        query_embedding = self.embedder.encode(query).tolist()

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        return results["documents"][0]
    
    def get_context(self, query: str):
        docs = self.search(query)
        if not docs:
            return ""
        # docs is expected to be a list of document strings
        return "\n\n".join(docs)