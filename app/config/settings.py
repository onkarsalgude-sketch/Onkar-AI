from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

STORAGE_DIR = BASE_DIR / "storage"

UPLOAD_DIR = STORAGE_DIR / "uploads"
VECTOR_DB_DIR = STORAGE_DIR / "vector_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

CHAT_DB = BASE_DIR / "app" / "database" / "chat_history.db"
MEMORY_DB = BASE_DIR / "app" / "database" / "memory.db"