from app.services.ollama_service import OllamaService
from app.memory.memory import add


class Brain:
    def __init__(self):
        self.ai = OllamaService()

    def chat(self, message):
        add("user", message)

        reply = self.ai.generate_reply(message)

        add("assistant", reply)

        return reply