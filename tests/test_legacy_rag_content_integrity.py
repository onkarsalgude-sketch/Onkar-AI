import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.legacy_rag_migration import (
    build_legacy_rag_plan,
)


class ExactContentCollection:
    def __init__(
        self,
        content: str,
    ):
        self.content = content

    def get(
        self,
        *,
        include,
    ):
        del include

        return {
            "ids": [
                "Example.pdf-0",
            ],
            "documents": [
                self.content,
            ],
            "metadatas": [
                {
                    "source": "Example.pdf",
                },
            ],
            "embeddings": [
                [
                    0.1,
                    0.2,
                    0.3,
                ],
            ],
        }


class LegacyRAGContentIntegrityTests(
    unittest.TestCase
):
    def test_surrounding_whitespace_is_preserved(
        self,
    ):
        exact_content = (
            "  Exact legacy chunk content.\n"
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "chat.db"
            )

            connection = sqlite3.connect(
                database_path
            )

            try:
                connection.execute(
                    """
                    CREATE TABLE documents (
                        document_id TEXT,
                        chat_id INTEGER,
                        filename TEXT,
                        file_hash TEXT,
                        page_count INTEGER,
                        chunk_count INTEGER,
                        status TEXT
                    )
                    """
                )

                connection.execute(
                    """
                    INSERT INTO documents
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "document-1",
                        1,
                        "Example.pdf",
                        "shared-file-hash",
                        1,
                        1,
                        "ready",
                    ),
                )

                connection.commit()

                plan = build_legacy_rag_plan(
                    connection,
                    ExactContentCollection(
                        exact_content
                    ),
                    embedding_dimension=3,
                )

            finally:
                connection.close()

        self.assertTrue(
            plan.can_execute
        )

        self.assertEqual(
            len(plan.targets),
            1,
        )

        source = plan.targets[0].source

        self.assertEqual(
            source.content,
            exact_content,
        )

        self.assertEqual(
            source.content_hash,
            hashlib.sha256(
                exact_content.encode(
                    "utf-8"
                )
            ).hexdigest(),
        )

        self.assertNotEqual(
            source.content,
            exact_content.strip(),
        )


if __name__ == "__main__":
    unittest.main()
