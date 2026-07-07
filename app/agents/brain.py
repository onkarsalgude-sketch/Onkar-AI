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
Answer the user using the internet information below.

User Question:
{message}

Internet Answer:
{search["answer"]}

Search Results:
{search["results"]}

Give a clear answer and include sources if available.
"""
            reply = self.ai.generate_reply(prompt)

        else:
            reply = self.ai.generate_reply(message)

        add("assistant", reply)
        return reply