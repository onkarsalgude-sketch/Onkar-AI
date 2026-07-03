from duckduckgo_search import DDGS


class SearchService:
    def search(self, query: str, max_results: int = 5) -> str:
        results_text = []

        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)

            for item in results:
                title = item.get("title", "")
                body = item.get("body", "")
                href = item.get("href", "")

                results_text.append(
                    f"Title: {title}\nSummary: {body}\nURL: {href}"
                )

        if not results_text:
            return "No internet search results found."

        return "\n\n".join(results_text)