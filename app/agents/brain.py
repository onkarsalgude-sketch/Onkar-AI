from app.services.groq_service import GroqService
from app.memory.memory import add
from app.agents.internet import InternetAgent
from app.agents.router import AgentRouter


class Brain:
    def __init__(self):
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

        # non-internet route
        return self.ai.generate_reply_stream(
            self.ai.build_prompt(message)
        )