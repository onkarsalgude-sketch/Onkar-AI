from app.services.groq_service import GroqService
from app.memory.memory import add
from app.services.document_service import get_selected_document_filenames
from app.agents.internet import InternetAgent
from app.agents.router import AgentRouter
from app.services.rag_service import RAGService
from app.services.knowledge_retrieval_service import (
    retrieve_knowledge_context,
)


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

        # PDF RAG - only selected PDFs from current chat
        if route == "pdf":
            selected_filenames = []

            if chat_id is not None and chat_id > 0:
                selected_filenames = (
                    get_selected_document_filenames(
                        chat_id
                    )
                )

            if not selected_filenames:
                return {
                    "route": "pdf",
                    "prompt": f"""
    User Question:
    {message}

    There are no selected PDF documents available in this chat.

    Tell the user:
    "No PDF is selected in this chat. Please upload or select a PDF first."
    """,
                    "sources": [],
                }

            rag_result = self.rag.search(
                query=message,
                chat_id=chat_id,
                filenames=selected_filenames,
            )

            if not rag_result["context"]:
                prompt = f"""
    User Question:
    {message}

    The selected PDFs do not contain readable information for this question.

    Tell the user:
    "The answer is not available in the selected PDFs."
    """
            else:
                prompt = f"""
    Use only the following content from the selected PDFs in the current chat.

    PDF Content:
    {rag_result["context"]}

    User Question:
    {message}

    Rules:
    1. Answer only using the selected PDF content.
    2. Do not use unselected PDFs.
    3. Do not use PDFs uploaded in other chats.
    4. If the answer is missing, clearly say:
       "The answer is not available in the selected PDFs."
    5. Mention the PDF filename and page number when useful.
    """

            return {
                "route": "pdf",
                "prompt": prompt,
                "sources": rag_result["sources"],
            }

        knowledge_result = retrieve_knowledge_context(
            message,
            limit=5,
        )

        if not knowledge_result["context"]:
            return {
                "route": "chat",
                "prompt": message,
                "sources": [],
            }

        prompt = f"""
    Use only the following content from the reusable Knowledge Library.

    Reusable Knowledge Library Context:
    {knowledge_result["context"]}

    User Question:
    {message}

    Rules:
    1. Ground the answer only in the reusable Knowledge Library context.
    2. Do not use chat-specific PDFs or PDFs from other chats.
    3. If the answer is missing, clearly say:
       "The answer is not available in the Knowledge Library."
    4. Mention the PDF filename and page number when useful.
    """

        return {
            "route": "knowledge",
            "prompt": prompt,
            "sources": knowledge_result["sources"],
        }

    def chat(
        self,
        message: str,
        chat_id: int | None = None,
        model_id: str | None = None,
    ) -> dict:
        add("user", message)

        prepared = self.prepare_request(
            message=message,
            chat_id=chat_id,
        )

        if prepared["route"] == "chat":
            reply = self.ai.generate_reply(
                message,
                model_id=model_id,
            )
        else:
            reply = self.ai.generate_reply(
                prepared["prompt"],
                model_id=model_id,
            )

        add("assistant", reply)

        return {
            "reply": reply,
            "sources": prepared["sources"],
            "model_id": self.ai.resolve_model(model_id),
        }

    def stream_chat(
        self,
        message: str,
        chat_id: int | None = None,
        model_id: str | None = None,
    ) -> dict:
        prepared = self.prepare_request(
            message=message,
            chat_id=chat_id,
        )

        if prepared["route"] == "chat":
            prompt = self.ai.build_prompt(message)
        else:
            prompt = prepared["prompt"]

        stream = self.ai.generate_reply_stream(
            prompt,
            model_id=model_id,
        )

        return {
            "stream": stream,
            "sources": prepared["sources"],
            "model_id": self.ai.resolve_model(model_id),
        }
