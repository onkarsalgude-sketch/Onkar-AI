import os

from dotenv import load_dotenv
from groq import Groq

from app.memory.memory import get


load_dotenv()


class GroqService:
    MODEL_OPTIONS = [
        {
            "id": "llama-3.1-8b-instant",
            "name": "Llama 3.1 8B",
            "description": "Fast responses",
        },
        {
            "id": "llama-3.3-70b-versatile",
            "name": "Llama 3.3 70B",
            "description": "Balanced quality",
        },
        {
            "id": "openai/gpt-oss-20b",
            "name": "GPT-OSS 20B",
            "description": "Fast reasoning",
        },
        {
            "id": "openai/gpt-oss-120b",
            "name": "GPT-OSS 120B",
            "description": "Advanced reasoning",
        },
    ]

    SUPPORTED_MODEL_IDS = {
        model["id"]
        for model in MODEL_OPTIONS
    }

    DEFAULT_MODEL = (
        "llama-3.3-70b-versatile"
    )

    def __init__(self):
        api_key = os.getenv(
            "GROQ_API_KEY"
        )

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured."
            )

        self.client = Groq(
            api_key=api_key
        )

        configured_model = os.getenv(
            "GROQ_MODEL",
            self.DEFAULT_MODEL,
        )

        self.default_model = (
            configured_model
            if configured_model
            in self.SUPPORTED_MODEL_IDS
            else self.DEFAULT_MODEL
        )

        # Existing code compatibility
        self.model = self.default_model

        self.vision_model = os.getenv(
            "GROQ_VISION_MODEL",
            (
                "meta-llama/"
                "llama-4-scout-17b-16e-instruct"
            ),
        )

    @classmethod
    def get_available_models(cls):
        return [
            dict(model)
            for model in cls.MODEL_OPTIONS
        ]

    def resolve_model(
        self,
        model_id: str | None = None,
    ) -> str:
        if (
            model_id
            and model_id
            in self.SUPPORTED_MODEL_IDS
        ):
            return model_id

        return self.default_model

    def build_prompt(
        self,
        message: str,
    ) -> str:
        memory = get()

        history_lines = [
            f"{role}: {text}"
            for role, text in memory
        ]

        history = "\n".join(
            history_lines
        )

        return f"""
You are Onkar AI, a helpful personal AI assistant.

Conversation history:
{history}

User Question:
{message}

Give a clear and simple answer.
""".strip()

    def generate_title(
        self,
        message: str,
        model_id: str | None = None,
    ) -> str:
        selected_model = (
            self.resolve_model(model_id)
        )

        response = (
            self.client.chat.completions.create(
                model=selected_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a very short "
                            "chat title, maximum "
                            "4 words. Return only "
                            "the title."
                        ),
                    },
                    {
                        "role": "user",
                        "content": message,
                    },
                ],
                temperature=0.3,
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
            .strip()
        )

    def generate_reply(
        self,
        message: str,
        model_id: str | None = None,
    ) -> str:
        selected_model = (
            self.resolve_model(model_id)
        )

        prompt = self.build_prompt(
            message
        )

        response = (
            self.client.chat.completions.create(
                model=selected_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.7,
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
        )

    def generate_reply_stream(
        self,
        prompt: str,
        model_id: str | None = None,
    ):
        selected_model = (
            self.resolve_model(model_id)
        )

        response = (
            self.client.chat.completions.create(
                model=selected_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.7,
                stream=True,
            )
        )

        for chunk in response:
            content = getattr(
                chunk.choices[0].delta,
                "content",
                None,
            )

            if content:
                yield content

    def analyze_image(
        self,
        image_url: str,
    ) -> str:
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
""".strip()

        response = (
            self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                },
                            },
                        ],
                    }
                ],
                temperature=0.4,
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
        )