import sqlite3
from datetime import datetime

DB_PATH = "app/chat_history.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_message(role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
        (role, content, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()


def get_messages(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {"role": row[0], "content": row[1], "created_at": row[2]}
        for row in reversed(rows)
    ]


def clear_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages")

    conn.commit()
    conn.close()