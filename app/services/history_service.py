import json
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

    # Chats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            folder_id INTEGER DEFAULT NULL
        )
    """)

    # Chat messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            model_id TEXT DEFAULT NULL,
            attachment_json TEXT DEFAULT NULL
        )
    """)

    # Uploaded PDF documents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            filename TEXT NOT NULL COLLATE NOCASE,
            file_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'processing',
            is_selected INTEGER NOT NULL DEFAULT 1,
            uploaded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, filename)
        )
    """)

    # Add missing columns to old chats table
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

    # Add backup metadata columns to old messages table
    cursor.execute("PRAGMA table_info(messages)")

    message_columns = {
        row[1]
        for row in cursor.fetchall()
    }

    if "sources_json" not in message_columns:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'
        """)

    if "model_id" not in message_columns:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN model_id TEXT DEFAULT NULL
        """)

    if "attachment_json" not in message_columns:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN attachment_json TEXT DEFAULT NULL
        """)

    # Indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chats_folder_id
        ON chats(folder_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chats_title
        ON chats(title COLLATE NOCASE)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_chat_id
        ON messages(chat_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_role
        ON messages(role)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_created_at
        ON messages(created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_chat_id
        ON documents(chat_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_selected
        ON documents(chat_id, is_selected)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_hash
        ON documents(chat_id, file_hash)
    """)

    conn.commit()
    conn.close()


def _to_iso_datetime(value):
    if value is None:
        return datetime.now().isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    text = str(value).strip()

    return text or datetime.now().isoformat()


def _load_json(value, default):
    if not value:
        return default

    try:
        return json.loads(value)
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return default


def _escape_like(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _build_search_snippet(
    text: str,
    query: str,
    context_length: int = 80,
) -> str:
    clean_text = " ".join(
        str(text or "").split()
    )

    if not clean_text:
        return ""

    match_index = clean_text.casefold().find(
        query.casefold()
    )

    if match_index < 0:
        return (
            clean_text[: context_length * 2]
            + (
                "…"
                if len(clean_text)
                > context_length * 2
                else ""
            )
        )

    start = max(
        0,
        match_index - context_length,
    )

    end = min(
        len(clean_text),
        match_index
        + len(query)
        + context_length,
    )

    prefix = "…" if start > 0 else ""
    suffix = (
        "…"
        if end < len(clean_text)
        else ""
    )

    return (
        prefix
        + clean_text[start:end]
        + suffix
    )


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


def search_chats(
    query: str,
    *,
    role: str | None = None,
    folder_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    search_text = str(
        query or ""
    ).strip()

    if not search_text:
        return []

    if role not in {
        None,
        "user",
        "assistant",
    }:
        raise ValueError(
            "Role must be 'user' or 'assistant'."
        )

    safe_limit = max(
        1,
        min(int(limit), 100),
    )

    like_pattern = (
        f"%{_escape_like(search_text)}%"
    )

    folder_clause = ""
    folder_parameters = []

    if folder_id == 0:
        folder_clause = (
            " AND chats.folder_id IS NULL"
        )

    elif (
        folder_id is not None
        and folder_id > 0
    ):
        folder_clause = (
            " AND chats.folder_id = ?"
        )

        folder_parameters.append(
            folder_id
        )

    result_queries = []
    parameters = []

    # Title results are included only when no role filter is active.
    if role is None:
        result_queries.append(
            f"""
            SELECT
                chats.id AS chat_id,
                chats.title AS chat_title,
                chats.created_at AS chat_created_at,
                chats.is_pinned AS is_pinned,
                chats.folder_id AS folder_id,
                folders.name AS folder_name,
                NULL AS message_id,
                NULL AS role,
                chats.title AS matched_text,
                chats.created_at AS matched_at,
                'title' AS match_type,
                0 AS match_rank
            FROM chats
            LEFT JOIN folders
                ON folders.id = chats.folder_id
            WHERE chats.title
                LIKE ? ESCAPE '\\'
                COLLATE NOCASE
                {folder_clause}
            """
        )

        parameters.append(
            like_pattern
        )

        parameters.extend(
            folder_parameters
        )

    message_role_clause = ""

    if role is not None:
        message_role_clause = (
            " AND messages.role = ?"
        )

    result_queries.append(
        f"""
        SELECT
            chats.id AS chat_id,
            chats.title AS chat_title,
            chats.created_at AS chat_created_at,
            chats.is_pinned AS is_pinned,
            chats.folder_id AS folder_id,
            folders.name AS folder_name,
            messages.id AS message_id,
            messages.role AS role,
            messages.content AS matched_text,
            messages.created_at AS matched_at,
            'message' AS match_type,
            1 AS match_rank
        FROM messages
        INNER JOIN chats
            ON chats.id = messages.chat_id
        LEFT JOIN folders
            ON folders.id = chats.folder_id
        WHERE messages.content
            LIKE ? ESCAPE '\\'
            COLLATE NOCASE
            {message_role_clause}
            {folder_clause}
        """
    )

    parameters.append(
        like_pattern
    )

    if role is not None:
        parameters.append(
            role
        )

    parameters.extend(
        folder_parameters
    )

    sql = f"""
        SELECT
            chat_id,
            chat_title,
            chat_created_at,
            is_pinned,
            folder_id,
            folder_name,
            message_id,
            role,
            matched_text,
            matched_at,
            match_type
        FROM (
            {" UNION ALL ".join(result_queries)}
        )
        ORDER BY
            match_rank ASC,
            is_pinned DESC,
            matched_at DESC,
            chat_id DESC
        LIMIT ?
    """

    parameters.append(
        safe_limit
    )

    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        sql,
        parameters,
    )

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        results.append(
            {
                "chat_id": row[0],
                "chat_title": row[1],
                "chat_created_at": row[2],
                "is_pinned": bool(row[3]),
                "folder_id": row[4],
                "folder_name": row[5],
                "message_id": row[6],
                "role": row[7],
                "snippet": _build_search_snippet(
                    row[8],
                    search_text,
                ),
                "matched_at": row[9],
                "match_type": row[10],
            }
        )

    return results


def save_message(
    chat_id: int,
    role: str,
    content: str,
    *,
    sources=None,
    model_id=None,
    attachment=None,
    created_at=None,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    sources_json = json.dumps(
        sources or [],
        ensure_ascii=False,
    )

    attachment_json = (
        json.dumps(
            attachment,
            ensure_ascii=False,
        )
        if attachment
        else None
    )

    cursor.execute(
        """
        INSERT INTO messages (
            chat_id,
            role,
            content,
            created_at,
            sources_json,
            model_id,
            attachment_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            role,
            content,
            _to_iso_datetime(created_at),
            sources_json,
            model_id,
            attachment_json,
        ),
    )

    conn.commit()
    conn.close()


def get_messages(
    chat_id: int,
    limit: int = 1000,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            role,
            content,
            created_at,
            sources_json,
            model_id,
            attachment_json
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

    messages = []

    for row in reversed(rows):
        sources = _load_json(
            row[4],
            [],
        )

        attachment = _load_json(
            row[6],
            None,
        )

        message = {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "created_at": row[3],
            "sources": sources,
            "model_id": row[5],
            "attachment": attachment,
        }

        if attachment:
            message["fileName"] = (
                attachment.get("filename")
            )

            message["fileType"] = (
                attachment.get("type")
            )

            message["fileSize"] = (
                attachment.get("size")
            )

        messages.append(message)

    return messages

def get_message(
    chat_id: int,
    message_id: int,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            chat_id,
            role,
            content,
            created_at,
            sources_json,
            model_id,
            attachment_json
        FROM messages
        WHERE id = ?
          AND chat_id = ?
        """,
        (
            message_id,
            chat_id,
        ),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "chat_id": row[1],
        "role": row[2],
        "content": row[3],
        "created_at": row[4],
        "sources": _load_json(
            row[5],
            [],
        ),
        "model_id": row[6],
        "attachment": _load_json(
            row[7],
            None,
        ),
    }


def edit_user_message(
    chat_id: int,
    message_id: int,
    content: str,
):
    cleaned_content = str(
        content or ""
    ).strip()

    if not cleaned_content:
        raise ValueError(
            "Message content cannot be empty."
        )

    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "BEGIN IMMEDIATE"
        )

        cursor.execute(
            """
            SELECT role
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                chat_id,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            conn.rollback()
            return None

        if row[0] != "user":
            raise ValueError(
                "Only user messages can be edited."
            )

        cursor.execute(
            """
            UPDATE messages
            SET content = ?
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                cleaned_content,
                message_id,
                chat_id,
            ),
        )

        # Edited message नंतरचे जुने responses
        # delete केले जातील, जेणेकरून नवीन
        # response योग्य context वर generate होईल.
        cursor.execute(
            """
            DELETE FROM messages
            WHERE chat_id = ?
              AND id > ?
            """,
            (
                chat_id,
                message_id,
            ),
        )

        deleted_following_messages = (
            cursor.rowcount
        )

        conn.commit()

        return {
            "chat_id": chat_id,
            "message_id": message_id,
            "content": cleaned_content,
            "deleted_following_messages": (
                deleted_following_messages
            ),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def delete_message(
    chat_id: int,
    message_id: int,
):
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "BEGIN IMMEDIATE"
        )

        cursor.execute(
            """
            SELECT role
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                chat_id,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            conn.rollback()
            return None

        role = row[0]

        cursor.execute(
            """
            DELETE FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                chat_id,
            ),
        )

        conn.commit()

        return {
            "chat_id": chat_id,
            "message_id": message_id,
            "role": role,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def restore_chat_backup(
    backup: dict,
):
    chat_data = backup.get(
        "chat",
        {},
    )

    model_data = backup.get(
        "model",
        {},
    ) or {}

    messages = backup.get(
        "messages",
        [],
    )

    title = str(
        chat_data.get("title")
        or "Imported Chat"
    ).strip()

    if not title:
        title = "Imported Chat"

    title = title[:200]

    chat_created_at = (
        _to_iso_datetime(
            chat_data.get("created_at")
        )
    )

    is_pinned = (
        1
        if chat_data.get("is_pinned")
        else 0
    )

    default_model_id = (
        model_data.get("selected_id")
    )

    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN")

        cursor.execute(
            """
            INSERT INTO chats (
                title,
                created_at,
                is_pinned,
                folder_id
            )
            VALUES (?, ?, ?, NULL)
            """,
            (
                title,
                chat_created_at,
                is_pinned,
            ),
        )

        chat_id = cursor.lastrowid

        has_pdf_metadata = False
        has_attachment_metadata = False

        for message in messages:
            role = message.get("role")
            content = str(
                message.get("content")
                or ""
            )

            message_sources = []

            for source in (
                message.get("sources")
                or []
            ):
                source_copy = dict(source)

                if source_copy.get(
                    "filename"
                ):
                    has_pdf_metadata = True

                    # Old chat ID must not be reused.
                    source_copy[
                        "chat_id"
                    ] = chat_id

                message_sources.append(
                    source_copy
                )

            attachment = (
                message.get("attachment")
            )

            if attachment:
                has_attachment_metadata = True

            message_model_id = (
                message.get("model_id")
            )

            if (
                not message_model_id
                and role == "assistant"
            ):
                message_model_id = (
                    default_model_id
                )

            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    model_id,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    role,
                    content,
                    _to_iso_datetime(
                        message.get(
                            "created_at"
                        )
                    ),
                    json.dumps(
                        message_sources,
                        ensure_ascii=False,
                    ),
                    message_model_id,
                    (
                        json.dumps(
                            attachment,
                            ensure_ascii=False,
                        )
                        if attachment
                        else None
                    ),
                ),
            )

        conn.commit()

        warnings = []

        if (
            chat_data.get("folder_id")
            or chat_data.get(
                "folder_name"
            )
        ):
            warnings.append(
                "The original folder was not restored."
            )

        if (
            has_pdf_metadata
            or has_attachment_metadata
        ):
            warnings.append(
                "Attachment metadata was restored, but the original files and PDF RAG data were not included in the backup."
            )

        return {
            "chat_id": chat_id,
            "title": title,
            "message_count": len(
                messages
            ),
            "warnings": warnings,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


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