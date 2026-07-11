import sqlite3
from datetime import datetime

from app.config.settings import CHAT_DB
from app.database.db import get_connection


DB_PATH = str(CHAT_DB)


def init_db():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    # Chat folders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            folder_id INTEGER DEFAULT NULL
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

    # जुन्या chats table मध्ये नवीन columns सुरक्षितपणे add करणे
    cursor.execute("PRAGMA table_info(chats)")

    chat_columns = {
        row[1]
        for row in cursor.fetchall()
    }

    if "is_pinned" not in chat_columns:
        cursor.execute("""
            ALTER TABLE chats
            ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0
        """)

    if "folder_id" not in chat_columns:
        cursor.execute("""
            ALTER TABLE chats
            ADD COLUMN folder_id INTEGER DEFAULT NULL
        """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chats_folder_id
        ON chats(folder_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_chat_id
        ON messages(chat_id)
    """)

    conn.commit()
    conn.close()


def create_chat(title="New Chat"):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chats (
            title,
            created_at,
            is_pinned,
            folder_id
        )
        VALUES (?, ?, 0, NULL)
        """,
        (
            title,
            datetime.now().isoformat(),
        ),
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
            chats.is_pinned,
            chats.folder_id,
            folders.name AS folder_name,
            (
                SELECT content
                FROM messages
                WHERE messages.chat_id = chats.id
                ORDER BY messages.id DESC
                LIMIT 1
            ) AS last_message
        FROM chats
        LEFT JOIN folders
            ON folders.id = chats.folder_id
        ORDER BY
            chats.is_pinned DESC,
            chats.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "is_pinned": bool(row[3]),
            "folder_id": row[4],
            "folder_name": row[5],
            "last_message": row[6] if row[6] else "",
        }
        for row in rows
    ]


def save_message(
    chat_id: int,
    role: str,
    content: str,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO messages (
            chat_id,
            role,
            content,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            chat_id,
            role,
            content,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()


def get_messages(
    chat_id: int,
    limit: int = 50,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            role,
            content,
            created_at
        FROM messages
        WHERE chat_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            chat_id,
            limit,
        ),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "role": row[0],
            "content": row[1],
            "created_at": row[2],
        }
        for row in reversed(rows)
    ]


def rename_chat(
    chat_id: int,
    title: str,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chats
        SET title = ?
        WHERE id = ?
        """,
        (
            title,
            chat_id,
        ),
    )

    conn.commit()
    conn.close()


def toggle_pin_chat(chat_id: int):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT is_pinned
        FROM chats
        WHERE id = ?
        """,
        (chat_id,),
    )

    row = cursor.fetchone()

    if row is None:
        conn.close()
        return None

    current_value = bool(row[0])
    new_value = 0 if current_value else 1

    cursor.execute(
        """
        UPDATE chats
        SET is_pinned = ?
        WHERE id = ?
        """,
        (
            new_value,
            chat_id,
        ),
    )

    conn.commit()
    conn.close()

    return bool(new_value)


# -------------------------
# Folder functions
# -------------------------

def get_folders():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            folders.id,
            folders.name,
            folders.created_at,
            COUNT(chats.id) AS chat_count
        FROM folders
        LEFT JOIN chats
            ON chats.folder_id = folders.id
        GROUP BY
            folders.id,
            folders.name,
            folders.created_at
        ORDER BY folders.name ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "name": row[1],
            "created_at": row[2],
            "chat_count": row[3],
        }
        for row in rows
    ]


def create_folder(name: str):
    folder_name = name.strip()

    if not folder_name:
        return None

    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        created_at = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO folders (
                name,
                created_at
            )
            VALUES (?, ?)
            """,
            (
                folder_name,
                created_at,
            ),
        )

        folder_id = cursor.lastrowid

        conn.commit()

        return {
            "id": folder_id,
            "name": folder_name,
            "created_at": created_at,
            "chat_count": 0,
        }

    except sqlite3.IntegrityError:
        conn.rollback()
        return None

    finally:
        conn.close()


def rename_folder(
    folder_id: int,
    name: str,
):
    folder_name = name.strip()

    if not folder_name:
        return False

    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE folders
            SET name = ?
            WHERE id = ?
            """,
            (
                folder_name,
                folder_id,
            ),
        )

        updated = cursor.rowcount > 0

        conn.commit()
        return updated

    except sqlite3.IntegrityError:
        conn.rollback()
        return False

    finally:
        conn.close()


def delete_folder(folder_id: int):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    # Folder delete करण्यापूर्वी chats बाहेर काढणे
    cursor.execute(
        """
        UPDATE chats
        SET folder_id = NULL
        WHERE folder_id = ?
        """,
        (folder_id,),
    )

    cursor.execute(
        """
        DELETE FROM folders
        WHERE id = ?
        """,
        (folder_id,),
    )

    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


def move_chat_to_folder(
    chat_id: int,
    folder_id: int | None,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    # folder_id None असेल तर chat folder मधून remove होईल
    if folder_id is not None:
        cursor.execute(
            """
            SELECT id
            FROM folders
            WHERE id = ?
            """,
            (folder_id,),
        )

        if cursor.fetchone() is None:
            conn.close()
            return False

    cursor.execute(
        """
        UPDATE chats
        SET folder_id = ?
        WHERE id = ?
        """,
        (
            folder_id,
            chat_id,
        ),
    )

    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return updated


def delete_chat(chat_id: int):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM messages
        WHERE chat_id = ?
        """,
        (chat_id,),
    )

    cursor.execute(
        """
        DELETE FROM chats
        WHERE id = ?
        """,
        (chat_id,),
    )

    conn.commit()
    conn.close()


def clear_history():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM chats")

    conn.commit()
    conn.close()