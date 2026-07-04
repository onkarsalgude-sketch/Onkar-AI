import os
from pypdf import PdfReader


class RAGService:
    def __init__(self):
        self.upload_dir = "app/uploads"
        self.context_file = "app/pdf_context.txt"

    def read_pdf(self, file_path):
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        return text

    def add_pdf(self, file_path):
        text = self.read_pdf(file_path)

        with open(self.context_file, "w", encoding="utf-8") as f:
            f.write(text)

        return {
            "message": "PDF indexed successfully",
            "chunks": len(text)
        }

    def get_context(self, query=None):
        if not os.path.exists(self.context_file):
            return ""

        with open(self.context_file, "r", encoding="utf-8") as f:
            return f.read()[:12000]