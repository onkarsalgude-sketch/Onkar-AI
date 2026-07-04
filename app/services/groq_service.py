import os
from groq import Groq
from dotenv import load_dotenv
from app.memory.memory import get

load_dotenv()


class GroqService:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def generate_reply(self, message):
        memory = get()

        history = ""
        for role, text in memory:
            history += f"{role}: {text}\n"

        prompt = f"""
You are Onkar AI, a helpful personal AI assistant.

Conversation history:
{history}

User Question:
{message}

Give a clear and simple answer.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        return response.choices[0].message.content