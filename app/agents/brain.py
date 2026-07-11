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

    def prepare_request(
        self,
        message: str,
        chat_id: int | None = None,
    ) -> dict:
        route = self.router.route(message)

        # Internet search
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
                "route": "internet",
                "prompt": prompt,
                "sources": search.get("sources", []),
            }

        # PDF RAG — फक्त current chat मधील PDFs
        if route == "pdf":
            rag_result = self.rag.search(
                query=message,
                chat_id=chat_id,
            )

            if not rag_result["context"]:
                prompt = f"""
User Question:
{message}

There is no readable PDF content available in this chat.

Tell the user:
"No PDF information is available in this chat. Please attach a PDF and send it first."
"""
            else:
                prompt = f"""
Use only the following PDF content from the current chat to answer the question.

PDF Content:
{rag_result["context"]}

User Question:
{message}

Rules:
1. Answer only using the PDF content provided above.
2. Do not use information from PDFs uploaded in other chats.
3. If the answer is not present, clearly say:
   "The answer is not available in the PDF attached to this chat."
4. When useful, mention the PDF filename and page number.
"""

            return {
                "route": "pdf",
                "prompt": prompt,
                "sources": rag_result["sources"],
            }

        # Normal chat
        return {
            "route": "chat",
            "prompt": message,
            "sources": [],
        }

    def chat(
        self,
        message: str,
        chat_id: int | None = None,
    ) -> dict:
        add("user", message)

        prepared = self.prepare_request(
            message=message,
            chat_id=chat_id,
        )

        if prepared["route"] == "chat":
            reply = self.ai.generate_reply(message)
        else:
            reply = self.ai.generate_reply(
                prepared["prompt"]
            )

        add("assistant", reply)

        return {
            "reply": reply,
            "sources": prepared["sources"],
        }

    def stream_chat(
        self,
        message: str,
        chat_id: int | None = None,
    ) -> dict:
        prepared = self.prepare_request(
            message=message,
            chat_id=chat_id,
        )

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