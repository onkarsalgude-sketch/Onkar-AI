import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config.settings import CHAT_DB
from app.database.db import get_runtime_connection


DB_PATH = str(CHAT_DB)


def calculate_file_hash(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


def get_document(
    document_id: str,
    chat_id: int,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            document_id,
            chat_id,
            filename,
            file_path,
            file_hash,
            file_size,
            page_count,
            chunk_count,
            status,
            is_selected,
            uploaded_at,
            updated_at
        FROM documents
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            document_id,
            chat_id,
        ),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "document_id": row[0],
        "chat_id": row[1],
        "filename": row[2],
        "file_path": row[3],
        "file_hash": row[4],
        "file_size": row[5],
        "page_count": row[6],
        "chunk_count": row[7],
        "status": row[8],
        "is_selected": bool(row[9]),
        "uploaded_at": row[10],
        "updated_at": row[11],
    }


def get_document_by_filename(
    chat_id: int,
    filename: str,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE chat_id = ?
          AND filename = ?
        """,
        (
            chat_id,
            Path(filename).name,
        ),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return get_document(
        document_id=row[0],
        chat_id=chat_id,
    )


def find_duplicate_document(
    chat_id: int,
    file_hash: str,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE chat_id = ?
          AND file_hash = ?
          AND status != 'failed'
        LIMIT 1
        """,
        (
            chat_id,
            file_hash,
        ),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return get_document(
        document_id=row[0],
        chat_id=chat_id,
    )


def create_document(
    chat_id: int,
    filename: str,
    file_path: str | Path,
    file_hash: str,
    file_size: int,
    document_id: str | None = None,
) -> dict:
    safe_filename = Path(filename).name
    now = datetime.now().isoformat()

    existing_document = get_document_by_filename(
        chat_id=chat_id,
        filename=safe_filename,
    )

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    if existing_document:
        document_id = existing_document[
            "document_id"
        ]

        cursor.execute(
            """
            UPDATE documents
            SET
                file_path = ?,
                file_hash = ?,
                file_size = ?,
                page_count = 0,
                chunk_count = 0,
                status = 'processing',
                is_selected = 1,
                updated_at = ?
            WHERE document_id = ?
              AND chat_id = ?
            """,
            (
                str(file_path),
                file_hash,
                file_size,
                now,
                document_id,
                chat_id,
            ),
        )

    else:
        document_id = (
            document_id
            or uuid4().hex
        )

        cursor.execute(
            """
            INSERT INTO documents (
                document_id,
                chat_id,
                filename,
                file_path,
                file_hash,
                file_size,
                page_count,
                chunk_count,
                status,
                is_selected,
                uploaded_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                0, 0, 'processing', 1, ?, ?
            )
            """,
            (
                document_id,
                chat_id,
                safe_filename,
                str(file_path),
                file_hash,
                file_size,
                now,
                now,
            ),
        )

    conn.commit()
    conn.close()

    return get_document(
        document_id=document_id,
        chat_id=chat_id,
    )


def mark_document_ready(
    document_id: str,
    chat_id: int,
    page_count: int,
    chunk_count: int,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET
            page_count = ?,
            chunk_count = ?,
            status = 'ready',
            updated_at = ?
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            page_count,
            chunk_count,
            datetime.now().isoformat(),
            document_id,
            chat_id,
        ),
    )

    conn.commit()
    conn.close()

    return get_document(
        document_id=document_id,
        chat_id=chat_id,
    )


def mark_document_failed(
    document_id: str,
    chat_id: int,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET
            status = 'failed',
            updated_at = ?
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            datetime.now().isoformat(),
            document_id,
            chat_id,
        ),
    )

    conn.commit()
    conn.close()

    return get_document(
        document_id=document_id,
        chat_id=chat_id,
    )



def mark_document_deleting(
    document_id: str,
    chat_id: int,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET
            status = 'deleting',
            is_selected = 0,
            updated_at = ?
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            datetime.now().isoformat(),
            document_id,
            chat_id,
        ),
    )

    conn.commit()
    conn.close()

    return get_document(
        document_id=document_id,
        chat_id=chat_id,
    )


def list_documents(chat_id: int) -> list[dict]:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE chat_id = ?
        ORDER BY uploaded_at DESC
        """,
        (chat_id,),
    )

    document_ids = [
        row[0]
        for row in cursor.fetchall()
    ]

    conn.close()

    documents = []

    for document_id in document_ids:
        document = get_document(
            document_id=document_id,
            chat_id=chat_id,
        )

        if document:
            documents.append(document)

    return documents


def set_document_selected(
    document_id: str,
    chat_id: int,
    is_selected: bool,
) -> dict | None:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET
            is_selected = ?,
            updated_at = ?
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            1 if is_selected else 0,
            datetime.now().isoformat(),
            document_id,
            chat_id,
        ),
    )

    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()

    if not updated:
        return None

    return get_document(
        document_id=document_id,
        chat_id=chat_id,
    )


def delete_document_record(
    document_id: str,
    chat_id: int,
) -> bool:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM documents
        WHERE document_id = ?
          AND chat_id = ?
        """,
        (
            document_id,
            chat_id,
        ),
    )

    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


def delete_chat_documents(chat_id: int) -> int:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM documents
        WHERE chat_id = ?
        """,
        (chat_id,),
    )

    deleted_count = cursor.rowcount

    conn.commit()
    conn.close()

    return deleted_count

def get_selected_document_filenames(
    chat_id: int,
) -> list[str]:
    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT filename
        FROM documents
        WHERE chat_id = ?
          AND is_selected = 1
          AND status = 'ready'
        ORDER BY uploaded_at DESC
        """,
        (chat_id,),
    )

    filenames = [
        row[0]
        for row in cursor.fetchall()
    ]

    conn.close()

    return filenames


def list_documents_by_statuses(
    statuses: tuple[str, ...],
) -> list[dict]:
    normalized_statuses = []

    for status in statuses:
        normalized = str(
            status
        ).strip().casefold()

        if (
            normalized
            and normalized
            not in normalized_statuses
        ):
            normalized_statuses.append(
                normalized
            )

    if not normalized_statuses:
        return []

    placeholders = ", ".join(
        "?"
        for _ in normalized_statuses
    )

    conn = get_runtime_connection(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            f"""
            SELECT
                document_id,
                chat_id
            FROM documents
            WHERE lower(status) IN (
                {placeholders}
            )
            ORDER BY
                updated_at ASC,
                document_id ASC
            """,
            tuple(normalized_statuses),
        )

        rows = cursor.fetchall()
    finally:
        conn.close()

    documents = []

    for document_id, chat_id in rows:
        document = get_document(
            document_id=str(
                document_id
            ),
            chat_id=int(chat_id),
        )

        if document is not None:
            documents.append(document)

    return documents
