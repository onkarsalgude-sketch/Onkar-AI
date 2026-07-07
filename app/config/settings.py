from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

APP_DIR = BASE_DIR / "app"

DATABASE_DIR = APP_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

CHAT_DB = DATABASE_DIR / "chat_history.db"
MEMORY_DB = DATABASE_DIR / "memory.db"

STORAGE_DIR = BASE_DIR / "storage"

UPLOAD_DIR = STORAGE_DIR / "uploads"
VECTOR_DB_DIR = STORAGE_DIR / "vector_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

PDF_CONTEXT_FILE = STORAGE_DIR / "pdf_context.txt"