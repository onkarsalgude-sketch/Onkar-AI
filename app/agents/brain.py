from app.services.groq_service import GroqService
from app.memory.memory import add


class Brain:
    def __init__(self):
        self.ai = GroqService()

    def chat(self, message):
        add("user", message)
        reply = self.ai.generate_reply(message)
        add("assistant", reply)
        return reply