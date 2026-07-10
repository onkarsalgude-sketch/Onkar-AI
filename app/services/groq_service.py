import os
from groq import Groq
from dotenv import load_dotenv
from app.memory.memory import get

load_dotenv()


class GroqService:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.vision_model = os.getenv(
            "GROQ_VISION_MODEL",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        )

    def build_prompt(self, message):
        memory = get()

        history = ""
        for role, text in memory:
            history += f"{role}: {text}\n"

        return f"""
You are Onkar AI, a helpful personal AI assistant.

Conversation history:
{history}

User Question:
{message}

Give a clear and simple answer.
"""

    def generate_title(self, message):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a very short chat title (maximum 4 words). "
                        "Return only the title."
                    ),
                },
                {"role": "user", "content": message},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

    def generate_reply(self, message):
        prompt = self.build_prompt(message)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        return response.choices[0].message.content

    def generate_reply_stream(self, prompt):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            stream=True,
        )

        for chunk in response:
            if getattr(chunk.choices[0].delta, "content", None):
                yield chunk.choices[0].delta.content

    def analyze_image(self, image_url: str):
        prompt = """
Analyze this image professionally.

If it is a resume:
- Candidate Name
- Education
- Skills
- Experience
- Projects
- Summary

If it is not a resume:
- Describe the image in bullet points.

Return the answer in proper Markdown format.
"""

        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            temperature=0.4,
        )

        return response.choices[0].message.content