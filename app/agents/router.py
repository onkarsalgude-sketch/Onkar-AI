class AgentRouter:
    def route(self, message: str):
        text = message.lower()

        internet_keywords = [
            "latest",
            "today",
            "news",
            "current",
            "live",
            "price",
            "weather",
            "stock",
            "search",
            "internet",
            "recent",
        ]

        pdf_keywords = [
            "pdf",
            "document",
            "resume",
            "file",
            "uploaded",
        ]

        if any(word in text for word in internet_keywords):
            return "internet"

        if any(word in text for word in pdf_keywords):
            return "pdf"

        return "chat"