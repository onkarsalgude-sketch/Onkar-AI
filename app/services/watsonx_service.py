import os
from dotenv import load_dotenv
from ibm_watsonx_ai.foundation_models import ModelInference

load_dotenv()


class WatsonxService:
    def __init__(self):
        self.api_key = os.getenv("WATSONX_API_KEY")
        self.project_id = os.getenv("WATSONX_PROJECT_ID")
        self.url = os.getenv("WATSONX_URL")
        self.model_id = os.getenv("WATSONX_MODEL_ID")

        self.model = ModelInference(
            model_id=self.model_id,
            credentials={
                "apikey": self.api_key,
                "url": self.url
            },
            project_id=self.project_id
        )

    def generate_reply(self, message: str) -> str:
        prompt = f"""
You are Onkar AI, a helpful personal AI assistant.
Answer clearly and simply.

User: {message}
Assistant:
"""

        response = self.model.generate_text(
            prompt=prompt,
            params={
                "max_new_tokens": 300,
                "temperature": 0.7
            }
        )

        return response