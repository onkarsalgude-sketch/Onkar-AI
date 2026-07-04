import os
from groq import Groq
from dotenv import load_dotenv

from app.services.rag_service import RAGService
from app.services.search_service import SearchService

load_dotenv()


class GroqService:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.rag = RAGService()
        self.search_service = SearchService()

    def generate_reply(self, message):
        pdf_context = self.rag.get_context(message)

        internet_context = ""
        if len(pdf_context.strip()) < 100:
            internet_context = self.search_service.search(message)

        prompt = f"""
You are Onkar AI, a helpful personal AI assistant.

PDF Context:
{pdf_context}

Internet Context:
{internet_context}

User Question:
{message}

Give a clear and simple answer.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )

        return response.choices[0].message.content