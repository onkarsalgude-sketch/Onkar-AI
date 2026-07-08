import os
from urllib.parse import urlparse

from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


class InternetAgent:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = TavilyClient(api_key=self.api_key)

    def get_domain(self, url: str):
        try:
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return ""

    def search(self, query: str):
        response = self.client.search(
            query=query,
            max_results=5,
            include_answer=True,
        )

        results = response.get("results", [])

        sources = []
        for item in results:
            sources.append({
                "title": item.get("title", "Source"),
                "url": item.get("url", ""),
                "domain": self.get_domain(item.get("url", "")),
            })

        return {
            "answer": response.get("answer", ""),
            "results": results,
            "sources": sources,
        }