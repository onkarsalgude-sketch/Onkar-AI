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

    def prepare_request(self, message: str) -> dict:
        route = self.router.route(message)

        if route == "internet":
            search = self.internet.search(message)

            prompt = f"""
Question:
{message}

Internet Information:
{search.get("answer", "")}

Answer naturally using the information above.
"""

            return {
                "route": route,
                "prompt": prompt,
                "sources": search.get("sources", []),
            }

        if route == "pdf":
            rag_result = self.rag.search(message)

            prompt = f"""
Use the following PDF content to answer the user question.

PDF Content:
{rag_result["context"]}

User Question:
{message}

Answer only using the uploaded PDF content.

If the answer is not available in the PDF, clearly say:
"The answer is not available in the uploaded document."

When useful, mention the source PDF name and page number.
"""

            return {
                "route": route,
                "prompt": prompt,
                "sources": rag_result["sources"],
            }

        return {
            "route": "chat",
            "prompt": message,
            "sources": [],
        }

    def chat(self, message: str) -> dict:
        add("user", message)

        prepared = self.prepare_request(message)

        if prepared["route"] == "chat":
            reply = self.ai.generate_reply(message)
        else:
            reply = self.ai.generate_reply(prepared["prompt"])

        add("assistant", reply)

        return {
            "reply": reply,
            "sources": prepared["sources"],
        }

    def stream_chat(self, message: str) -> dict:
        prepared = self.prepare_request(message)

        if prepared["route"] == "chat":
            stream = self.ai.generate_reply_stream(
                self.ai.build_prompt(message)
            )
        else:
            stream = self.ai.generate_reply_stream(
                prepared["prompt"]
            )

        return {
            "stream": stream,
            "sources": prepared["sources"],
        }