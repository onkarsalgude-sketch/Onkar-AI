import unittest

from app.config.rag import (
    load_rag_settings,
)
from app.services.pgvector_rag_store import (
    PgVectorChunk,
    PgVectorRAGStore,
    PgVectorRAGStoreError,
)


POSTGRES_URL = (
    "postgresql://"
    "user:secret@"
    "db.example.com:5432/onkar"
)


def settings():
    return load_rag_settings(
        {
            "DATABASE_URL": (
                POSTGRES_URL
            ),
            "RAG_BACKEND": (
                "pgvector"
            ),
            "RAG_EMBEDDING_DIMENSION": (
                "3"
            ),
        }
    )


class FakeCursor:
    def __init__(
        self,
        owner,
    ):
        self.owner = owner
        self.rowcount = 0
        self.rows = []
        self.closed = False

    def execute(
        self,
        sql,
        parameters=(),
    ):
        self.owner.execute_count += 1

        normalized = " ".join(
            str(sql).split()
        )

        self.owner.statements.append(
            (
                normalized,
                tuple(parameters),
            )
        )

        if (
            self.owner.fail_at
            == self.owner.execute_count
        ):
            raise RuntimeError(
                "postgresql://"
                "user:private-secret@host/db"
            )

        normalized_upper = (
            normalized.upper()
        )

        if normalized_upper.startswith(
            "DELETE"
        ):
            self.rowcount = (
                self.owner.delete_rowcount
            )

        if normalized_upper.startswith(
            "SELECT COUNT"
        ):
            self.rows = [
                (
                    self.owner.count_value,
                )
            ]

        elif normalized_upper.startswith(
            "SELECT"
        ):
            self.rows = list(
                self.owner.search_rows
            )

        return self

    def fetchall(self):
        return list(
            self.rows
        )

    def fetchone(self):
        if not self.rows:
            return None

        return self.rows[0]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(
        self,
        *,
        fail_at=None,
        delete_rowcount=0,
        count_value=0,
        search_rows=(),
    ):
        self.fail_at = fail_at
        self.delete_rowcount = (
            delete_rowcount
        )
        self.count_value = count_value
        self.search_rows = search_rows
        self.execute_count = 0
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursor_instance = None

    def cursor(self):
        self.cursor_instance = (
            FakeCursor(self)
        )

        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def chunk(
    *,
    chunk_id="chunk-1",
    chat_id=7,
    document_id="doc-1",
    filename="Report.pdf",
    page=1,
    chunk_index=0,
    content="Useful content",
    embedding=(0.1, 0.2, 0.3),
):
    return PgVectorChunk(
        chunk_id=chunk_id,
        chat_id=chat_id,
        document_id=document_id,
        filename=filename,
        page=page,
        chunk_index=chunk_index,
        content=content,
        embedding=embedding,
    )


class PgVectorRAGStoreTests(
    unittest.TestCase
):
    def test_chroma_settings_are_rejected(
        self,
    ):
        with self.assertRaises(
            PgVectorRAGStoreError
        ):
            PgVectorRAGStore(
                load_rag_settings({})
            )

    def test_replace_document_chunks_is_transactional(
        self,
    ):
        connection = FakeConnection()

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: connection
            ),
        )

        inserted = (
            store.replace_document_chunks(
                [
                    chunk(),
                    chunk(
                        chunk_id="chunk-2",
                        page=2,
                        chunk_index=1,
                    ),
                ],
                chat_id=7,
                document_id="doc-1",
            )
        )

        self.assertEqual(
            inserted,
            2,
        )

        self.assertTrue(
            connection.committed
        )

        self.assertFalse(
            connection.rolled_back
        )

        self.assertEqual(
            len(connection.statements),
            3,
        )

        self.assertIn(
            "DELETE FROM public.rag_chunks",
            connection.statements[0][0],
        )

        self.assertIn(
            "CAST(? AS vector)",
            connection.statements[1][0],
        )

        self.assertEqual(
            connection.statements[1][1][8],
            "[0.10000000000000001,"
            "0.20000000000000001,"
            "0.29999999999999999]",
        )

    def test_replace_rejects_mixed_document_chunks(
        self,
    ):
        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: FakeConnection()
            ),
        )

        with self.assertRaises(
            PgVectorRAGStoreError
        ):
            store.replace_document_chunks(
                [
                    chunk(
                        document_id="other-doc"
                    )
                ],
                chat_id=7,
                document_id="doc-1",
            )

    def test_invalid_embedding_dimension_is_rejected(
        self,
    ):
        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: FakeConnection()
            ),
        )

        with self.assertRaises(
            PgVectorRAGStoreError
        ):
            store.replace_document_chunks(
                [
                    chunk(
                        embedding=(
                            0.1,
                            0.2,
                        )
                    )
                ],
                chat_id=7,
                document_id="doc-1",
            )

    def test_write_failure_rolls_back_and_sanitizes_error(
        self,
    ):
        connection = FakeConnection(
            fail_at=2
        )

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: connection
            ),
        )

        with self.assertRaises(
            PgVectorRAGStoreError
        ) as context:
            store.replace_document_chunks(
                [chunk()],
                chat_id=7,
                document_id="doc-1",
            )

        self.assertTrue(
            connection.rolled_back
        )

        self.assertFalse(
            connection.committed
        )

        self.assertNotIn(
            "private-secret",
            str(context.exception),
        )

    def test_search_uses_chat_filename_and_cosine_scope(
        self,
    ):
        connection = FakeConnection(
            search_rows=[
                (
                    "Relevant content",
                    "Report.pdf",
                    3,
                    "doc-1",
                    2,
                    0.125,
                )
            ]
        )

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: connection
            ),
        )

        results = store.search(
            (0.4, 0.5, 0.6),
            chat_id=7,
            filenames=[
                "Report.pdf",
                "report.pdf",
            ],
            limit=5,
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0]["page"],
            3,
        )

        self.assertEqual(
            results[0]["distance"],
            0.125,
        )

        sql, parameters = (
            connection.statements[0]
        )

        self.assertIn(
            "<=> CAST(? AS vector)",
            sql,
        )

        self.assertIn(
            "collection_name = ?",
            sql,
        )

        self.assertIn(
            "chat_id = ?",
            sql,
        )

        self.assertIn(
            "lower(filename) IN",
            sql,
        )

        self.assertIn(
            "pdf_documents",
            parameters,
        )

        self.assertIn(
            7,
            parameters,
        )

    def test_empty_filename_filter_returns_without_database_call(
        self,
    ):
        connection = FakeConnection()

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: connection
            ),
        )

        results = store.search(
            (0.1, 0.2, 0.3),
            chat_id=7,
            filenames=[],
        )

        self.assertEqual(
            results,
            [],
        )

        self.assertEqual(
            connection.statements,
            [],
        )

    def test_delete_operations_commit_row_counts(
        self,
    ):
        connections = [
            FakeConnection(
                delete_rowcount=4
            ),
            FakeConnection(
                delete_rowcount=3
            ),
            FakeConnection(
                delete_rowcount=2
            ),
        ]

        iterator = iter(connections)

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: next(iterator)
            ),
        )

        self.assertEqual(
            store.delete_document(
                chat_id=7,
                document_id="doc-1",
            ),
            4,
        )

        self.assertEqual(
            store.delete_filename(
                chat_id=7,
                filename="Report.pdf",
            ),
            3,
        )

        self.assertEqual(
            store.delete_chat(
                chat_id=7
            ),
            2,
        )

        self.assertTrue(
            all(
                item.committed
                for item in connections
            )
        )

    def test_count_uses_collection_and_chat_scope(
        self,
    ):
        connection = FakeConnection(
            count_value=9
        )

        store = PgVectorRAGStore(
            settings(),
            connection_factory=(
                lambda: connection
            ),
        )

        self.assertEqual(
            store.count(
                chat_id=7
            ),
            9,
        )

        sql, parameters = (
            connection.statements[0]
        )

        self.assertIn(
            "SELECT COUNT(*)",
            sql,
        )

        self.assertEqual(
            parameters,
            (
                "pdf_documents",
                7,
            ),
        )


if __name__ == "__main__":
    unittest.main()
