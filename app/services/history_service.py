import json
import sqlite3
from datetime import datetime

from app.config.settings import CHAT_DB
from app.config.database import (
    load_database_settings,
)
from app.database.db import (
    DATABASE_INTEGRITY_ERRORS,
    begin_write_transaction,
    get_connection as get_legacy_connection,
    get_runtime_connection,
)
from app.database.engine import (
    build_database_engine,
)
from app.database.migrations import (
    initialize_schema,
)
from app.services.branch_merge_service import (
    BRANCH_MERGE_PREVIEW_VERSION,
    _build_branch_merge_preview_token,
    _build_canonical_branch_turns,
    _is_positive_integer,
)


DB_PATH = str(CHAT_DB)


def init_db():
    conn = get_legacy_connection(DB_PATH)
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
            folder_id INTEGER DEFAULT NULL,
            parent_chat_id INTEGER DEFAULT NULL,
            branched_from_message_id INTEGER DEFAULT NULL,
            branch_message_id INTEGER DEFAULT NULL
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

    # Message bookmarks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL UNIQUE,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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

    # Branch merge audit and idempotency state. These tables intentionally
    # omit foreign keys so completed audit records can survive chat deletion.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS branch_merge_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            request_fingerprint TEXT NOT NULL,
            preview_token TEXT NOT NULL,
            branch_chat_id INTEGER NOT NULL,
            parent_chat_id INTEGER NOT NULL,
            branched_from_message_id INTEGER NOT NULL,
            branch_message_id INTEGER NOT NULL,
            expected_parent_last_message_id INTEGER NOT NULL,
            expected_branch_last_message_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN ('pending', 'completed')
            ),
            inserted_turn_count INTEGER NOT NULL DEFAULT 0,
            inserted_message_count INTEGER NOT NULL DEFAULT 0,
            first_created_parent_message_id INTEGER DEFAULT NULL,
            last_created_parent_message_id INTEGER DEFAULT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT DEFAULT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS branch_merge_message_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merge_operation_id INTEGER NOT NULL,
            branch_chat_id INTEGER NOT NULL,
            parent_chat_id INTEGER NOT NULL,
            turn_key TEXT NOT NULL,
            turn_position INTEGER NOT NULL,
            message_position INTEGER NOT NULL,
            source_branch_message_id INTEGER NOT NULL,
            created_parent_message_id INTEGER NOT NULL UNIQUE,
            created_message_fingerprint TEXT NOT NULL,
            UNIQUE(
                merge_operation_id,
                source_branch_message_id
            ),
            UNIQUE(
                branch_chat_id,
                parent_chat_id,
                source_branch_message_id
            )
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

    if "parent_chat_id" not in chat_columns:
        cursor.execute("""
            ALTER TABLE chats
            ADD COLUMN parent_chat_id INTEGER DEFAULT NULL
        """)

    if "branched_from_message_id" not in chat_columns:
        cursor.execute("""
            ALTER TABLE chats
            ADD COLUMN branched_from_message_id INTEGER DEFAULT NULL
        """)

    if "branch_message_id" not in chat_columns:
        cursor.execute("""
            ALTER TABLE chats
            ADD COLUMN branch_message_id INTEGER DEFAULT NULL
        """)

    # Best-effort backfill for branches created before branch_message_id
    # was persisted. Only an exact, unique child-message match is safe.
    cursor.execute("""
        SELECT
            id,
            parent_chat_id,
            branched_from_message_id
        FROM chats
        WHERE parent_chat_id IS NOT NULL
          AND branched_from_message_id IS NOT NULL
          AND branch_message_id IS NULL
    """)

    legacy_branch_rows = cursor.fetchall()

    for (
        branch_chat_id,
        parent_chat_id,
        source_message_id,
    ) in legacy_branch_rows:
        savepoint_name = (
            f"backfill_branch_{branch_chat_id}"
        )

        try:
            cursor.execute(
                f"SAVEPOINT {savepoint_name}"
            )

            cursor.execute(
                """
                SELECT
                    role,
                    content,
                    created_at
                FROM messages
                WHERE id = ?
                  AND chat_id = ?
                """,
                (
                    source_message_id,
                    parent_chat_id,
                ),
            )

            source_message = cursor.fetchone()

            if source_message is not None:
                cursor.execute(
                    """
                    SELECT id
                    FROM messages
                    WHERE chat_id = ?
                      AND role = ?
                      AND content = ?
                      AND created_at = ?
                    """,
                    (
                        branch_chat_id,
                        source_message[0],
                        source_message[1],
                        source_message[2],
                    ),
                )

                matching_messages = (
                    cursor.fetchall()
                )

                if len(matching_messages) == 1:
                    cursor.execute(
                        """
                        UPDATE chats
                        SET branch_message_id = ?
                        WHERE id = ?
                          AND branch_message_id IS NULL
                        """,
                        (
                            matching_messages[0][0],
                            branch_chat_id,
                        ),
                    )

            cursor.execute(
                f"RELEASE SAVEPOINT {savepoint_name}"
            )

        except sqlite3.Error as error:
            try:
                cursor.execute(
                    f"ROLLBACK TO SAVEPOINT {savepoint_name}"
                )
                cursor.execute(
                    f"RELEASE SAVEPOINT {savepoint_name}"
                )
            except sqlite3.Error:
                pass

            print(
                "BRANCH MESSAGE BACKFILL ERROR "
                f"FOR CHAT {branch_chat_id}:",
                error,
            )

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
        CREATE INDEX IF NOT EXISTS idx_chats_parent_chat_id
        ON chats(parent_chat_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chats_branched_message_id
        ON chats(branched_from_message_id)
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
        CREATE INDEX IF NOT EXISTS idx_message_bookmarks_chat_id
        ON message_bookmarks(chat_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_bookmarks_created_at
        ON message_bookmarks(created_at)
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

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_branch_merge_operations_branch
        ON branch_merge_operations(branch_chat_id, completed_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_branch_merge_operations_parent
        ON branch_merge_operations(parent_chat_id, completed_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_branch_merge_mappings_operation
        ON branch_merge_message_mappings(merge_operation_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_branch_merge_mappings_chats
        ON branch_merge_message_mappings(branch_chat_id, parent_chat_id)
    """)

    conn.commit()
    conn.close()




_legacy_init_db = init_db


def init_db():
    """Initialize and safely migrate the configured database schema."""
    settings = load_database_settings(
        default_sqlite_path=DB_PATH,
    )

    if settings.is_sqlite:
        _legacy_init_db()

    engine = build_database_engine(
        settings
    )

    try:
        initialize_schema(
            engine
        )
    finally:
        engine.dispose()


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


def _has_meaningful_json_metadata(value):
    if value is None:
        return False

    try:
        if isinstance(value, (bytes, bytearray)):
            text = bytes(value).decode("utf-8").strip()
        else:
            text = str(value).strip()
    except Exception:
        return True

    if not text:
        return False

    try:
        parsed_value = json.loads(text)
    except Exception:
        return True

    if parsed_value is None:
        return False

    if isinstance(
        parsed_value,
        (dict, list, str),
    ):
        return bool(parsed_value)

    return True


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
    conn = get_runtime_connection(DB_PATH)
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

def create_chat_branch(
    parent_chat_id: int,
    message_id: int,
    title: str | None = None,
):
    cleaned_title = str(
        title or ""
    ).strip()

    if len(cleaned_title) > 200:
        raise ValueError(
            "Branch title cannot exceed 200 characters."
        )

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        begin_write_transaction(conn)

        cursor.execute(
            """
            SELECT
                title,
                folder_id
            FROM chats
            WHERE id = ?
            """,
            (parent_chat_id,),
        )

        parent_chat = cursor.fetchone()

        if parent_chat is None:
            conn.rollback()
            return None

        cursor.execute(
            """
            SELECT
                role,
                content
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                parent_chat_id,
            ),
        )

        source_message = cursor.fetchone()

        if source_message is None:
            conn.rollback()
            return None

        if source_message[0] != "user":
            raise ValueError(
                "A conversation branch can only be created from a user message."
            )

        parent_title = parent_chat[0]
        parent_folder_id = parent_chat[1]

        branch_title = (
            cleaned_title
            or f"{parent_title} (Branch)"
        )

        branch_title = (
            branch_title[:200].strip()
            or "Branched Chat"
        )

        created_at = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO chats (
                title,
                created_at,
                is_pinned,
                folder_id,
                parent_chat_id,
                branched_from_message_id,
                branch_message_id
            )
            VALUES (?, ?, 0, ?, ?, ?, NULL)
            """,
            (
                branch_title,
                created_at,
                parent_folder_id,
                parent_chat_id,
                message_id,
            ),
        )

        branch_chat_id = cursor.lastrowid

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM messages
            WHERE chat_id = ?
              AND id <= ?
            """,
            (
                parent_chat_id,
                message_id,
            ),
        )

        copied_message_count = cursor.fetchone()[0]

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
            SELECT
                ?,
                role,
                content,
                created_at,
                sources_json,
                model_id,
                attachment_json
            FROM messages
            WHERE chat_id = ?
              AND id <= ?
            ORDER BY id ASC
            """,
            (
                branch_chat_id,
                parent_chat_id,
                message_id,
            ),
        )
        cursor.execute(
            """
            SELECT id
            FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (branch_chat_id,),
        )

        branch_message_row = (
            cursor.fetchone()
        )

        branch_message_id = (
            branch_message_row[0]
            if branch_message_row
            else None
        )

        if branch_message_id is None:
            raise RuntimeError(
                "Unable to identify the copied branch source message."
            )

        cursor.execute(
            """
            UPDATE chats
            SET branch_message_id = ?
            WHERE id = ?
            """,
            (
                branch_message_id,
                branch_chat_id,
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "Unable to persist the copied branch source message."
            )

        conn.commit()

        return {
            "chat_id": branch_chat_id,
            "title": branch_title,
            "parent_chat_id": parent_chat_id,
            "parent_chat_title": parent_title,
            "branched_from_message_id": message_id,
            "branch_message_id": branch_message_id,
            "branched_from_message_role": source_message[0],
            "branched_from_message_content": source_message[1],
            "copied_message_count": copied_message_count,
            "folder_id": parent_folder_id,
            "created_at": created_at,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def compare_chat_with_parent(
    branch_chat_id: int,
):
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    def positive_id(value):
        return (
            value
            if _is_positive_integer(value)
            else None
        )

    def comparison_message(row):
        if row is None:
            return None

        return {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "created_at": row[3],
            "has_source_metadata": (
                _has_meaningful_json_metadata(
                    row[4]
                )
            ),
            "has_attachment_metadata": (
                _has_meaningful_json_metadata(
                    row[5]
                )
            ),
        }

    try:
        cursor.execute("BEGIN")

        cursor.execute(
            """
            SELECT
                branch_chats.id,
                branch_chats.title,
                branch_chats.parent_chat_id,
                branch_chats.branched_from_message_id,
                branch_chats.branch_message_id,
                parent_chats.id,
                parent_chats.title
            FROM chats AS branch_chats
            LEFT JOIN chats AS parent_chats
                ON parent_chats.id = branch_chats.parent_chat_id
            WHERE branch_chats.id = ?
            """,
            (branch_chat_id,),
        )

        chat_row = cursor.fetchone()

        if chat_row is None:
            conn.commit()
            return None

        branch_summary = {
            "id": chat_row[0],
            "title": chat_row[1],
        }

        parent_chat_id = positive_id(
            chat_row[2]
        )
        parent_message_id = positive_id(
            chat_row[3]
        )
        branch_message_id = positive_id(
            chat_row[4]
        )

        parent_summary = (
            {
                "id": chat_row[5],
                "title": chat_row[6],
            }
            if chat_row[5] is not None
            else None
        )

        def unavailable(
            reason,
            *,
            parent_source_message=None,
            branch_source_message=None,
        ):
            result = {
                "comparable": False,
                "reason": reason,
                "parent_chat": parent_summary,
                "branch_chat": branch_summary,
                "branched_from_message_id": (
                    parent_message_id
                ),
                "branch_message_id": (
                    branch_message_id
                ),
                "parent_source_message": (
                    parent_source_message
                ),
                "branch_source_message": (
                    branch_source_message
                ),
                "common_messages": [],
                "parent_only_messages": [],
                "branch_only_messages": [],
                "counts": None,
                "merge_preview": None,
            }

            conn.commit()
            return result

        if parent_chat_id is None:
            return unavailable(
                "detached_branch"
            )

        if parent_summary is None:
            return unavailable(
                "parent_missing"
            )

        if parent_message_id is None:
            return unavailable(
                "parent_boundary_missing"
            )

        if branch_message_id is None:
            return unavailable(
                "branch_boundary_missing"
            )

        cursor.execute(
            """
            SELECT
                id,
                role,
                content,
                created_at,
                sources_json,
                attachment_json
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                parent_message_id,
                parent_chat_id,
            ),
        )

        parent_source_message = (
            comparison_message(
                cursor.fetchone()
            )
        )

        cursor.execute(
            """
            SELECT
                id,
                role,
                content,
                created_at,
                sources_json,
                attachment_json
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                branch_message_id,
                branch_chat_id,
            ),
        )

        branch_source_message = (
            comparison_message(
                cursor.fetchone()
            )
        )

        if parent_source_message is None:
            return unavailable(
                "parent_source_message_missing",
                branch_source_message=(
                    branch_source_message
                ),
            )

        if branch_source_message is None:
            return unavailable(
                "branch_source_message_missing",
                parent_source_message=(
                    parent_source_message
                ),
            )

        def load_messages(
            chat_id,
            operator,
            boundary_message_id,
        ):
            if operator not in {"<=", ">"}:
                raise ValueError(
                    "Invalid comparison operator."
                )

            cursor.execute(
                f"""
                SELECT
                    id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    attachment_json
                FROM messages
                WHERE chat_id = ?
                  AND id {operator} ?
                ORDER BY id ASC
                """,
                (
                    chat_id,
                    boundary_message_id,
                ),
            )

            return [
                comparison_message(row)
                for row in cursor.fetchall()
            ]

        common_messages = load_messages(
            branch_chat_id,
            "<=",
            branch_message_id,
        )

        parent_only_messages = load_messages(
            parent_chat_id,
            ">",
            parent_message_id,
        )

        branch_only_messages = load_messages(
            branch_chat_id,
            ">",
            branch_message_id,
        )

        cursor.execute(
            """
            SELECT source_branch_message_id
            FROM branch_merge_message_mappings
            WHERE branch_chat_id = ?
              AND parent_chat_id = ?
            ORDER BY source_branch_message_id ASC
            """,
            (
                branch_chat_id,
                parent_chat_id,
            ),
        )

        already_merged_message_ids = [
            row[0]
            for row in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT COALESCE(MAX(id), 0)
            FROM messages
            WHERE chat_id = ?
            """,
            (parent_chat_id,),
        )
        expected_parent_last_message_id = (
            cursor.fetchone()[0]
        )

        cursor.execute(
            """
            SELECT COALESCE(MAX(id), 0)
            FROM messages
            WHERE chat_id = ?
            """,
            (branch_chat_id,),
        )
        expected_branch_last_message_id = (
            cursor.fetchone()[0]
        )

        merge_preview_turns = (
            _build_canonical_branch_turns(
                branch_message_id,
                branch_source_message,
                branch_only_messages,
                already_merged_message_ids,
            )
        )

        preview_token = (
            _build_branch_merge_preview_token(
                version=(
                    BRANCH_MERGE_PREVIEW_VERSION
                ),
                branch_chat_id=(
                    branch_summary["id"]
                ),
                branch_chat_title=(
                    branch_summary["title"]
                ),
                parent_chat_id=(
                    parent_summary["id"]
                ),
                parent_chat_title=(
                    parent_summary["title"]
                ),
                branched_from_message_id=(
                    parent_message_id
                ),
                branch_message_id=(
                    branch_message_id
                ),
                parent_source_message=(
                    parent_source_message
                ),
                branch_source_message=(
                    branch_source_message
                ),
                parent_only_messages=(
                    parent_only_messages
                ),
                branch_only_messages=(
                    branch_only_messages
                ),
                expected_parent_last_message_id=(
                    expected_parent_last_message_id
                ),
                expected_branch_last_message_id=(
                    expected_branch_last_message_id
                ),
                already_merged_source_message_ids=(
                    already_merged_message_ids
                ),
                turns=merge_preview_turns,
            )
        )

        result = {
            "comparable": True,
            "reason": None,
            "parent_chat": parent_summary,
            "branch_chat": branch_summary,
            "branched_from_message_id": (
                parent_message_id
            ),
            "branch_message_id": (
                branch_message_id
            ),
            "parent_source_message": (
                parent_source_message
            ),
            "branch_source_message": (
                branch_source_message
            ),
            "common_messages": common_messages,
            "parent_only_messages": (
                parent_only_messages
            ),
            "branch_only_messages": (
                branch_only_messages
            ),
            "counts": {
                "common": len(common_messages),
                "parent_only": len(
                    parent_only_messages
                ),
                "branch_only": len(
                    branch_only_messages
                ),
            },
            "merge_preview": {
                "version": (
                    BRANCH_MERGE_PREVIEW_VERSION
                ),
                "preview_token": preview_token,
                "expected_parent_last_message_id": (
                    expected_parent_last_message_id
                ),
                "expected_branch_last_message_id": (
                    expected_branch_last_message_id
                ),
                "turns": merge_preview_turns,
            },
        }

        conn.commit()
        return result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def get_chats():
    conn = get_runtime_connection(DB_PATH)
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
            ) AS last_message,
            chats.parent_chat_id,
            parent_chats.title AS parent_chat_title,
            chats.branched_from_message_id,
            chats.branch_message_id,
            (
                SELECT COUNT(*)
                FROM chats AS child_chats
                WHERE child_chats.parent_chat_id = chats.id
            ) AS branch_count
        FROM chats
        LEFT JOIN folders
            ON folders.id = chats.folder_id
        LEFT JOIN chats AS parent_chats
            ON parent_chats.id = chats.parent_chat_id
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
            "parent_chat_id": row[7],
            "parent_chat_title": row[8],
            "branched_from_message_id": row[9],
            "branch_message_id": row[10],
            "is_branch": row[7] is not None,
            "branch_count": row[11],
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

    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            messages.id,
            messages.role,
            messages.content,
            messages.created_at,
            messages.sources_json,
            messages.model_id,
            messages.attachment_json,
            message_bookmarks.id AS bookmark_id,
            message_bookmarks.note AS bookmark_note,
            message_bookmarks.created_at AS bookmarked_at,
            message_bookmarks.updated_at AS bookmark_updated_at
        FROM messages
        LEFT JOIN message_bookmarks
            ON message_bookmarks.message_id = messages.id
        WHERE messages.chat_id = ?
        ORDER BY messages.id DESC
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
            "is_bookmarked": (
                row[7] is not None
            ),
            "bookmark_id": row[7],
            "bookmark_note": (
                row[8] or ""
            ),
            "bookmarked_at": row[9],
            "bookmark_updated_at": row[10],
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
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            messages.id,
            messages.chat_id,
            messages.role,
            messages.content,
            messages.created_at,
            messages.sources_json,
            messages.model_id,
            messages.attachment_json,
            message_bookmarks.id AS bookmark_id,
            message_bookmarks.note AS bookmark_note,
            message_bookmarks.created_at AS bookmarked_at,
            message_bookmarks.updated_at AS bookmark_updated_at
        FROM messages
        LEFT JOIN message_bookmarks
            ON message_bookmarks.message_id = messages.id
        WHERE messages.id = ?
          AND messages.chat_id = ?
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
        "is_bookmarked": (
            row[8] is not None
        ),
        "bookmark_id": row[8],
        "bookmark_note": (
            row[9] or ""
        ),
        "bookmarked_at": row[10],
        "bookmark_updated_at": row[11],
    }

def save_message_bookmark(
    chat_id: int,
    message_id: int,
    note: str = "",
):
    cleaned_note = str(
        note or ""
    ).strip()

    if len(cleaned_note) > 1000:
        raise ValueError(
            "Bookmark note cannot exceed 1000 characters."
        )

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        begin_write_transaction(conn)

        cursor.execute(
            """
            SELECT
                role,
                content,
                created_at
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                chat_id,
            ),
        )

        message_row = cursor.fetchone()

        if message_row is None:
            conn.rollback()
            return None

        now = datetime.now().isoformat()

        cursor.execute(
            """
            SELECT
                id,
                created_at
            FROM message_bookmarks
            WHERE message_id = ?
            """,
            (message_id,),
        )

        bookmark_row = cursor.fetchone()

        if bookmark_row is None:
            cursor.execute(
                """
                INSERT INTO message_bookmarks (
                    chat_id,
                    message_id,
                    note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    message_id,
                    cleaned_note,
                    now,
                    now,
                ),
            )

            bookmark_id = cursor.lastrowid
            created_at = now

        else:
            bookmark_id = bookmark_row[0]
            created_at = bookmark_row[1]

            cursor.execute(
                """
                UPDATE message_bookmarks
                SET
                    chat_id = ?,
                    note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    chat_id,
                    cleaned_note,
                    now,
                    bookmark_id,
                ),
            )

        conn.commit()

        return {
            "bookmark_id": bookmark_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "role": message_row[0],
            "content": message_row[1],
            "message_created_at": message_row[2],
            "note": cleaned_note,
            "created_at": created_at,
            "updated_at": now,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def remove_message_bookmark(
    chat_id: int,
    message_id: int,
):
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM message_bookmarks
        WHERE chat_id = ?
          AND message_id = ?
        """,
        (
            chat_id,
            message_id,
        ),
    )

    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    if not deleted:
        return None

    return {
        "chat_id": chat_id,
        "message_id": message_id,
    }


def get_message_bookmarks(
    query: str | None = None,
    *,
    role: str | None = None,
    folder_id: int | None = None,
    limit: int = 100,
):
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
        min(int(limit), 200),
    )

    search_text = str(
        query or ""
    ).strip()

    where_clauses = []
    parameters = []

    if role is not None:
        where_clauses.append(
            "messages.role = ?"
        )
        parameters.append(role)

    if folder_id == 0:
        where_clauses.append(
            "chats.folder_id IS NULL"
        )

    elif (
        folder_id is not None
        and folder_id > 0
    ):
        where_clauses.append(
            "chats.folder_id = ?"
        )
        parameters.append(folder_id)

    if search_text:
        like_pattern = (
            f"%{_escape_like(search_text)}%"
        )

        where_clauses.append(
            """
            (
                message_bookmarks.note
                    LIKE ? ESCAPE '\\'
                    COLLATE NOCASE
                OR messages.content
                    LIKE ? ESCAPE '\\'
                    COLLATE NOCASE
                OR chats.title
                    LIKE ? ESCAPE '\\'
                    COLLATE NOCASE
            )
            """
        )

        parameters.extend(
            [
                like_pattern,
                like_pattern,
                like_pattern,
            ]
        )

    where_sql = ""

    if where_clauses:
        where_sql = (
            "WHERE "
            + " AND ".join(
                where_clauses
            )
        )

    parameters.append(safe_limit)

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        f"""
        SELECT
            message_bookmarks.id,
            message_bookmarks.chat_id,
            message_bookmarks.message_id,
            message_bookmarks.note,
            message_bookmarks.created_at,
            message_bookmarks.updated_at,
            messages.role,
            messages.content,
            messages.created_at,
            chats.title,
            chats.folder_id,
            folders.name
        FROM message_bookmarks
        INNER JOIN messages
            ON messages.id =
                message_bookmarks.message_id
        INNER JOIN chats
            ON chats.id =
                message_bookmarks.chat_id
        LEFT JOIN folders
            ON folders.id =
                chats.folder_id
        {where_sql}
        ORDER BY
            message_bookmarks.updated_at DESC,
            message_bookmarks.id DESC
        LIMIT ?
        """,
        parameters,
    )

    rows = cursor.fetchall()
    conn.close()

    bookmarks = []

    for row in rows:
        bookmarks.append(
            {
                "bookmark_id": row[0],
                "chat_id": row[1],
                "message_id": row[2],
                "note": row[3] or "",
                "created_at": row[4],
                "updated_at": row[5],
                "role": row[6],
                "content": row[7],
                "snippet": _build_search_snippet(
                    row[7],
                    search_text,
                ),
                "message_created_at": row[8],
                "chat_title": row[9],
                "folder_id": row[10],
                "folder_name": row[11],
            }
        )

    return bookmarks

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

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        begin_write_transaction(conn)

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
            DELETE FROM message_bookmarks
            WHERE chat_id = ?
              AND message_id = ?
            """,
            (
                chat_id,
                message_id,
            ),
        )

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
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        begin_write_transaction(conn)

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

    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
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

    conn = get_runtime_connection(DB_PATH)
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

    except DATABASE_INTEGRITY_ERRORS:
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

    conn = get_runtime_connection(DB_PATH)
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

    except DATABASE_INTEGRITY_ERRORS:
        conn.rollback()
        return False

    finally:
        conn.close()


def delete_folder(folder_id: int):
    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
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
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        begin_write_transaction(conn)

        cursor.execute(
            """
            UPDATE chats
            SET
                parent_chat_id = NULL,
                branched_from_message_id = NULL,
                branch_message_id = NULL
            WHERE parent_chat_id = ?
            """,
            (chat_id,),
        )

        cursor.execute(
            """
            DELETE FROM message_bookmarks
            WHERE chat_id = ?
            """,
            (chat_id,),
        )

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

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def clear_history():
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM message_bookmarks"
    )

    cursor.execute(
        "DELETE FROM messages"
    )

    cursor.execute(
        "DELETE FROM chats"
    )

    conn.commit()
    conn.close()
