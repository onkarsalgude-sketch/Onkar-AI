import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.document_migration_service import (
    DocumentMigrationError,
    build_document_migration_plan,
    execute_document_migration,
)
from app.services.document_service import (
    calculate_file_hash,
)
from app.storage.document_storage import (
    LocalDocumentStorage,
)


def create_database(
    path: Path,
) -> None:
    connection = sqlite3.connect(
        path
    )

    connection.execute(
        """
        CREATE TABLE documents (
            document_id TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT,
            file_hash TEXT,
            file_size INTEGER,
            status TEXT,
            updated_at TEXT
        )
        """
    )

    connection.commit()
    connection.close()


def insert_document(
    path: Path,
    *,
    document_id: str,
    chat_id: int,
    filename: str,
    file_path: str,
    content: bytes,
    status: str = "ready",
    file_hash: str | None = None,
    file_size: int | None = None,
) -> None:
    connection = sqlite3.connect(
        path
    )

    connection.execute(
        """
        INSERT INTO documents (
            document_id,
            chat_id,
            filename,
            file_path,
            file_hash,
            file_size,
            status,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, '')
        """,
        (
            document_id,
            chat_id,
            filename,
            file_path,
            (
                file_hash
                if file_hash is not None
                else calculate_file_hash(
                    content
                )
            ),
            (
                file_size
                if file_size is not None
                else len(content)
            ),
            status,
        ),
    )

    connection.commit()
    connection.close()


class FailingUpdateCursor:
    def __init__(
        self,
        inner,
        owner,
    ):
        self.inner = inner
        self.owner = owner

    def execute(
        self,
        sql,
        parameters=(),
    ):
        if (
            sql.strip()
            .upper()
            .startswith(
                "UPDATE DOCUMENTS"
            )
        ):
            self.owner.update_count += 1

            if self.owner.update_count == 2:
                raise RuntimeError(
                    "injected update failure"
                )

        self.inner.execute(
            sql,
            parameters,
        )

        return self

    def fetchall(self):
        return self.inner.fetchall()

    @property
    def rowcount(self):
        return self.inner.rowcount

    def close(self):
        self.inner.close()


class FailingUpdateConnection:
    def __init__(
        self,
        inner,
    ):
        self.inner = inner
        self.update_count = 0

    def cursor(self):
        return FailingUpdateCursor(
            self.inner.cursor(),
            self,
        )

    def commit(self):
        self.inner.commit()

    def rollback(self):
        self.inner.rollback()

    def close(self):
        self.inner.close()


class DocumentMigrationTests(
    unittest.TestCase
):
    def test_missing_source_is_reported(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "chat.db"

            create_database(
                database_path
            )

            content = (
                b"%PDF-1.4\nmissing\n%%EOF"
            )

            insert_document(
                database_path,
                document_id="doc-missing",
                chat_id=1,
                filename="missing.pdf",
                file_path=str(
                    root / "gone.pdf"
                ),
                content=content,
            )

            storage = LocalDocumentStorage(
                root / "objects"
            )

            connection = sqlite3.connect(
                database_path
            )

            try:
                plan = (
                    build_document_migration_plan(
                        connection,
                        storage,
                        source_roots=[
                            root / "legacy"
                        ],
                    )
                )
            finally:
                connection.close()

            self.assertEqual(
                len(plan.ready),
                0,
            )

            self.assertEqual(
                len(plan.missing),
                1,
            )

            self.assertFalse(
                plan.can_execute
            )

    def test_execute_is_idempotent(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "chat.db"
            legacy_root = root / "legacy"

            create_database(
                database_path
            )

            content = (
                b"%PDF-1.4\n"
                b"idempotent\n"
                b"%%EOF"
            )

            source_path = (
                legacy_root
                / "chat_12"
                / "report.pdf"
            )

            source_path.parent.mkdir(
                parents=True
            )

            source_path.write_bytes(
                content
            )

            insert_document(
                database_path,
                document_id="doc-12",
                chat_id=12,
                filename="report.pdf",
                file_path=str(
                    root / "old"
                    / "report.pdf"
                ),
                content=content,
            )

            storage = LocalDocumentStorage(
                root / "objects"
            )

            connection = sqlite3.connect(
                database_path
            )

            plan = build_document_migration_plan(
                connection,
                storage,
                source_roots=[
                    legacy_root
                ],
            )

            report = execute_document_migration(
                plan,
                connection,
                storage,
            )

            connection.close()

            self.assertEqual(
                report.migrated,
                1,
            )

            self.assertEqual(
                report.created_objects,
                1,
            )

            verify_connection = (
                sqlite3.connect(
                    database_path
                )
            )

            row = verify_connection.execute(
                """
                SELECT file_path
                FROM documents
                WHERE document_id = ?
                """,
                ("doc-12",),
            ).fetchone()

            self.assertTrue(
                row[0].startswith(
                    "chats/12/documents/"
                )
            )

            second_plan = (
                build_document_migration_plan(
                    verify_connection,
                    storage,
                    source_roots=[
                        legacy_root
                    ],
                )
            )

            verify_connection.close()

            self.assertEqual(
                len(
                    second_plan.already_migrated
                ),
                1,
            )

            self.assertEqual(
                len(second_plan.ready),
                0,
            )

    def test_metadata_mismatch_is_invalid(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "chat.db"
            legacy_root = root / "legacy"

            create_database(
                database_path
            )

            content = (
                b"%PDF-1.4\n"
                b"metadata\n"
                b"%%EOF"
            )

            source_path = (
                legacy_root
                / "chat_4"
                / "metadata.pdf"
            )

            source_path.parent.mkdir(
                parents=True
            )

            source_path.write_bytes(
                content
            )

            insert_document(
                database_path,
                document_id="doc-4",
                chat_id=4,
                filename="metadata.pdf",
                file_path=str(
                    root / "missing.pdf"
                ),
                content=content,
                file_hash="0" * 64,
            )

            storage = LocalDocumentStorage(
                root / "objects"
            )

            connection = sqlite3.connect(
                database_path
            )

            try:
                plan = (
                    build_document_migration_plan(
                        connection,
                        storage,
                        source_roots=[
                            legacy_root
                        ],
                    )
                )
            finally:
                connection.close()

            self.assertEqual(
                len(plan.invalid),
                1,
            )

            self.assertFalse(
                plan.can_execute
            )

    def test_failure_rolls_back_database_and_objects(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "chat.db"
            legacy_root = root / "legacy"

            create_database(
                database_path
            )

            original_references = []

            for index in (1, 2):
                content = (
                    b"%PDF-1.4\n"
                    + f"rollback-{index}\n".encode()
                    + b"%%EOF"
                )

                filename = (
                    f"rollback-{index}.pdf"
                )

                source_path = (
                    legacy_root
                    / "chat_9"
                    / filename
                )

                source_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                source_path.write_bytes(
                    content
                )

                original_reference = str(
                    root
                    / "old"
                    / filename
                )

                original_references.append(
                    original_reference
                )

                insert_document(
                    database_path,
                    document_id=(
                        f"doc-{index}"
                    ),
                    chat_id=9,
                    filename=filename,
                    file_path=(
                        original_reference
                    ),
                    content=content,
                )

            storage = LocalDocumentStorage(
                root / "objects"
            )

            plan_connection = sqlite3.connect(
                database_path
            )

            plan = build_document_migration_plan(
                plan_connection,
                storage,
                source_roots=[
                    legacy_root
                ],
            )

            plan_connection.close()

            inner_connection = sqlite3.connect(
                database_path
            )

            failing_connection = (
                FailingUpdateConnection(
                    inner_connection
                )
            )

            with self.assertRaises(
                DocumentMigrationError
            ):
                execute_document_migration(
                    plan,
                    failing_connection,
                    storage,
                )

            failing_connection.close()

            verify_connection = (
                sqlite3.connect(
                    database_path
                )
            )

            rows = verify_connection.execute(
                """
                SELECT file_path
                FROM documents
                ORDER BY document_id
                """
            ).fetchall()

            verify_connection.close()

            self.assertEqual(
                [
                    row[0]
                    for row in rows
                ],
                original_references,
            )

            stored_files = [
                path
                for path in (
                    storage.root.rglob("*")
                )
                if path.is_file()
            ]

            self.assertEqual(
                stored_files,
                [],
            )


if __name__ == "__main__":
    unittest.main()
