import sqlite3
from datetime import datetime

from app.config.settings import CHAT_DB
from app.database.db import get_connection

DB_PATH = str(CHAT_DB)

def init_db():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def create_chat(title="New Chat"):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO chats (title, created_at) VALUES (?, ?)",
        (title, datetime.now().isoformat())
    )

    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return chat_id


def get_chats():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            chats.id,
            chats.title,
            chats.created_at,
            (
                SELECT content
                FROM messages
                WHERE messages.chat_id = chats.id
                ORDER BY id DESC
                LIMIT 1
            ) AS last_message
        FROM chats
        ORDER BY chats.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "last_message": row[3] if row[3] else "",
        }
        for row in rows
    ]


def save_message(chat_id: int, role: str, content: str):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()


def get_messages(chat_id: int, limit: int = 50):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, content, created_at FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
        (chat_id, limit)
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {"role": row[0], "content": row[1], "created_at": row[2]}
        for row in reversed(rows)
    ]


def rename_chat(chat_id: int, title: str):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE chats SET title=? WHERE id=?",
        (title, chat_id)
    )

    conn.commit()
    conn.close()


def delete_chat(chat_id: int):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    cursor.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    conn.commit()
    conn.close()


def clear_history():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM chats")

    conn.commit()
    conn.close()