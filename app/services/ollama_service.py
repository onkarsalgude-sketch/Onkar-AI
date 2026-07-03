import importlib

from app.memory.memory import history
from app.services.rag_service import RAGService
from app.services.search_service import SearchService

try:
    ollama = importlib.import_module("ollama")
except ImportError:
    ollama = None


class OllamaService:

    def __init__(self):
        self.rag = RAGService()
        self.search_service = SearchService()

    def generate_reply(self, message):
        if ollama is None:
            raise RuntimeError("Install ollama package first.")

        pdf_context = self.rag.get_context(message)

        internet_context = ""
        if len(pdf_context.strip()) < 100:
            internet_context = self.search_service.search(message)

        prompt = f"""
You are Onkar AI, a helpful personal AI assistant.

Use PDF context if relevant.
If PDF context is weak or missing, use internet context.

PDF Context:
{pdf_context}

Internet Context:
{internet_context}

User Question:
{message}

Give a clear and simple answer.
"""

        messages = history().copy()
        messages.append({
            "role": "user",
            "content": prompt
        })

        response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        return response["message"]["content"]

    def generate_reply_stream(self, message):
        if ollama is None:
            raise RuntimeError("Install ollama package first.")

        pdf_context = self.rag.get_context(message)

        internet_context = ""
        if len(pdf_context.strip()) < 100:
            internet_context = self.search_service.search(message)

        prompt = f"""
You are Onkar AI, a helpful personal AI assistant.

Use PDF context if relevant.
If PDF context is weak or missing, use internet context.

PDF Context:
{pdf_context}

Internet Context:
{internet_context}

User Question:
{message}

Give a clear and simple answer.
"""

        messages = history().copy()
        messages.append({
            "role": "user",
            "content": prompt
        })

        stream = ollama.chat(
            model="llama3.2:3b",
            messages=messages,
            stream=True
        )

        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text