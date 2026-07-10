from app.services.groq_service import GroqService
from app.memory.memory import add
from app.agents.internet import InternetAgent
from app.agents.router import AgentRouter
from app.services.rag_service import RAGService

class Brain:
    def __init__(self):
        self.rag = RAGService()
        self.ai = GroqService()
        self.internet = InternetAgent()
        self.router = AgentRouter()

    def chat(self, message):
        add("user", message)

        route = self.router.route(message)

        if route == "internet":
            search = self.internet.search(message)

            prompt = f"""
Question:
{message}

Internet Information:
{search['answer']}

Answer naturally using the information above.
"""

            reply = self.ai.generate_reply(prompt)

            add("assistant", reply)

            return {
                "reply": reply,
                "sources": search["sources"],
            }

        if route == "pdf":
            pdf_context = self.rag.get_context(message)

            prompt = f"""
Use the following PDF content to answer the user question.

PDF Content:
{pdf_context}

User Question:
{message}

If the answer is not available in the PDF, say that it is not available in the uploaded document.
"""

            reply = self.ai.generate_reply(prompt)

            add("assistant", reply)

            return {
                "reply": reply,
                "sources": [],
            }

        reply = self.ai.generate_reply(message)

        add("assistant", reply)

        return {
            "reply": reply,
            "sources": [],
        }
    def stream_chat(self, message):
        route = self.router.route(message)

        if route == "internet":
            search = self.internet.search(message)

            prompt = f"""
Question:
{message}

Internet Information:
{search['answer']}

Answer naturally.
"""

            return self.ai.generate_reply_stream(prompt)

        if route == "pdf":
            pdf_context = self.rag.get_context(message)

            prompt = f"""
Use the following PDF content to answer the user question.

PDF Content:
{pdf_context}

User Question:
{message}

If the answer is not available in the PDF, say that it is not available in the uploaded document.
"""

            return self.ai.generate_reply_stream(prompt)

        # non-internet route
        return self.ai.generate_reply_stream(
            self.ai.build_prompt(message)
        )