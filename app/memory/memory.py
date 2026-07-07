import sqlite3

from app.config.settings import MEMORY_DB
from app.database.db import get_connection

DB = str(MEMORY_DB)


def init_memory():
    conn = get_connection(DB)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT,
        content TEXT
    )
    """)

    conn.commit()
    conn.close()


def add(role, content):
    conn = get_connection(DB)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO memory(role, content) VALUES(?, ?)",
        (role, content)
    )

    conn.commit()
    conn.close()


def get(limit=10):
    conn = get_connection(DB)
    cur = conn.cursor()

    cur.execute(
        "SELECT role, content FROM memory ORDER BY id DESC LIMIT ?",
        (limit,)
    )

    rows = cur.fetchall()
    conn.close()

    rows.reverse()
    return rows


def clear():
    conn = get_connection(DB)
    cur = conn.cursor()

    cur.execute("DELETE FROM memory")

    conn.commit()
    conn.close()


init_memory()