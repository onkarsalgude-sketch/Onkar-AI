import importlib

from app.memory.memory import history
from app.services.rag_service import RAGService

try:
    ollama = importlib.import_module("ollama")
except ImportError:
    ollama = None


class OllamaService:

    def __init__(self):
        self.rag = RAGService()

    def generate_reply(self, message):

        if ollama is None:
            raise RuntimeError("Install ollama package first.")

        # Search PDF knowledge
        context = self.rag.get_context(message)

        # Build prompt
        prompt = f"""
You are Onkar AI.

Answer the user's question using the context below.

Context:
{context}

Question:
{message}

If the answer is present in the context, answer only from the context.
If it is not present, answer using your general knowledge.
"""

        # Copy chat history
        messages = history().copy()

        # Add RAG prompt
        messages.append({
            "role": "user",
            "content": prompt
        })

        # Call Ollama
        response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        return response["message"]["content"]