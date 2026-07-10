from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

BASE_DIR = Path(__file__).resolve().parent.parent.parent

APP_DIR = BASE_DIR / "app"

DATABASE_DIR = APP_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

CHAT_DB = DATABASE_DIR / "chat_history.db"
MEMORY_DB = DATABASE_DIR / "memory.db"

STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = STORAGE_DIR / "uploads"
VECTOR_DB_DIR = STORAGE_DIR / "vector_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

PDF_STORAGE_DIR = STORAGE_DIR / "pdfs"
PDF_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

VECTOR_DB_DIR = STORAGE_DIR / "vector_db"
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

PDF_CONTEXT_FILE = STORAGE_DIR / "pdf_context.txt"