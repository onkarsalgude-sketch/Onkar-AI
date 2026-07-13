import re


class AgentRouter:
    def _matches_any(
        self,
        text: str,
        patterns: list[str],
    ) -> bool:
        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        )

    def route(self, message: str) -> str:
        text = " ".join(
            str(message).lower().split()
        )

        if not text:
            return "chat"

        # ---------------------------------
        # 1. Explicit internet search intent
        # ---------------------------------
        explicit_internet_patterns = [
            r"\bsearch\s+(the\s+)?(web|internet|online)\b",
            r"\b(search|browse|find|look\s*up)\b.*\b(web|internet|online)\b",
            r"\b(web|internet|online)\b.*\b(search|browse|find|look\s*up)\b",
            r"\bgoogle\s+(this|it|for)\b",
        ]

        explicit_internet_phrases = [
            "search online",
            "browse the web",
            "browse internet",
            "look it up online",
            "internet var search",
            "web var search",
            "इंटरनेटवर शोध",
            "वेबवर शोध",
            "ऑनलाइन शोध",
        ]

        if (
            self._matches_any(
                text,
                explicit_internet_patterns,
            )
            or any(
                phrase in text
                for phrase in explicit_internet_phrases
            )
        ):
            return "internet"

        # -----------------------------
        # 2. Uploaded PDF/document intent
        # -----------------------------
        document_terms = [
            "pdf",
            "document",
            "uploaded file",
            "attached file",
            "uploaded document",
            "attached document",
            "uploaded pdf",
            "attached pdf",
            "this file",
            "this document",
            "this pdf",
            "certificate",
            "certification",
            "course",
            "resume",
        ]

        document_actions = [
            "summarize",
            "summary",
            "analyse",
            "analyze",
            "review",
            "read",
            "extract",
            "explain",
            "compare",
            "find",
            "answer",
            "questions",
            "candidate",
            "resume",
            "skills",
            "education",
            "experience",
            "mention",
            "mentioned",
            "complete",
            "completed",
            "earned",
            "awarded",
            "issued",
        ]

        has_document_term = any(
            term in text
            for term in document_terms
        )

        has_document_action = any(
            action in text
            for action in document_actions
        )

        explicit_pdf_phrases = [
            "use the pdf uploaded in this chat",
            "pdf uploaded in this chat",
            "document uploaded in this chat",
            "summarize the pdf",
            "summarise the pdf",
            "read the pdf",
            "analyze the pdf",
            "analyse the pdf",
            "review the pdf",
            "extract from the pdf",
            "according to the pdf",
            "based on the pdf",
            "from the uploaded pdf",
            "from this document",
        ]

        if (
            any(
                phrase in text
                for phrase in explicit_pdf_phrases
            )
            or (
                has_document_term
                and has_document_action
            )
        ):
            return "pdf"

        # --------------------------
        # 3. Current/live information
        # --------------------------
        live_information_patterns = [
            r"\b(weather|forecast|temperature)\b",
            r"\b(latest|recent|breaking)\s+news\b",
            r"\b(stock|share|crypto|bitcoin|ethereum)\b.*\b(price|rate|news|update|chart)\b",
            r"\b(price|rate|score|result|schedule|traffic)\b.*\b(today|now|current|latest|live)\b",
            r"\b(today|now|current|latest|live)\b.*\b(price|rate|score|result|schedule|traffic|news|weather)\b",
            r"\b(latest|current|newest|recent)\b.*\b(version|release|update|status)\b",
            r"\b(current|present)\b.*\b(president|prime minister|ceo|governor|minister|chairman|captain)\b",
        ]

        live_information_phrases = [
            "today's news",
            "today news",
            "current news",
            "latest update",
            "live score",
            "current price",
            "today price",
            "share price",
            "stock price",
            "crypto price",
            "exchange rate",
            "आजचे हवामान",
            "आजची बातमी",
            "ताज्या बातम्या",
            "सध्याची किंमत",
            "आजचा भाव",
            "लाईव्ह स्कोअर",
            "aajcha bhav",
            "sadhyachi kimat",
        ]

        if (
            self._matches_any(
                text,
                live_information_patterns,
            )
            or any(
                phrase in text
                for phrase in live_information_phrases
            )
        ):
            return "internet"

        # --------------------------
        # 4. Normal AI conversation
        # --------------------------
        return "chat"