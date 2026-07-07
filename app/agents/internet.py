import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


class InternetAgent:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = TavilyClient(api_key=self.api_key)

    def search(self, query: str):
        response = self.client.search(
            query=query,
            max_results=5,
            include_answer=True,
        )

        return {
            "answer": response.get("answer", ""),
            "results": response.get("results", []),
        }