import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.legacy_rag_migration import (
    LegacyRAGMigrationError,
    build_legacy_rag_plan,
    execute_legacy_rag_migration,
)


def create_source_database(
    path: Path,
    *,
    mismatched_hash=False,
) -> None:
    connection = sqlite3.connect(
        path
    )

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

    resume_hashes = [
        "resume-hash"
        for _ in range(5)
    ]

    if mismatched_hash:
        resume_hashes[-1] = (
            "different-hash"
        )

    for index, chat_id in enumerate(
        (52, 58, 59, 60, 61)
    ):
        connection.execute(
            """
            INSERT INTO documents
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"resume-doc-{index}",
                chat_id,
                "Example_Resume_Onkar.pdf",
                resume_hashes[index],
                1,
                1,
                "ready",
            ),
        )

    connection.execute(
        """
        INSERT INTO documents
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "certificate-doc",
            52,
            (
                "Completion Certificate "
                "_ SkillsBuild "
                "Cybersecurity.pdf"
            ),
            "certificate-hash",
            1,
            1,
            "ready",
        ),
    )

    connection.commit()
    connection.close()


class FakeCollection:
    def __init__(
        self,
        *,
        divergent=False,
    ):
        self.ids = [
            (
                "Example_Resume_"
                "Onkar.pdf-0"
            )
        ]

        for index in range(5):
            self.ids.append(
                (
                    "Example_Resume_"
                    "Onkar.pdf-0-"
                    f"0000000{index}-"
                    "0000-0000-0000-"
                    "000000000000"
                )
            )

        self.documents = [
            "Resume content"
            for _ in self.ids
        ]

        self.metadatas = [
            {
                "source": (
                    "Example_Resume_"
                    "Onkar.pdf"
                )
            }
            for _ in self.ids
        ]

        self.embeddings = [
            [0.1, 0.2, 0.3]
            for _ in self.ids
        ]

        if divergent:
            self.embeddings[-1] = [
                0.9,
                0.8,
                0.7,
            ]

    def get(
        self,
        *,
        include,
    ):
        del include

        return {
            "ids": list(
                self.ids
            ),
            "documents": list(
                self.documents
            ),
            "metadatas": list(
                self.metadatas
            ),
            "embeddings": list(
                self.embeddings
            ),
        }


class FakeTargetCursor:
    def __init__(
        self,
        owner,
    ):
        self.owner = owner
        self.current_row = None
        self.rowcount = 0
        self.closed = False

    def execute(
        self,
        sql,
        parameters=(),
    ):
        normalized = " ".join(
            str(sql).split()
        )

        upper = normalized.upper()

        self.owner.statements.append(
            (
                normalized,
                tuple(parameters),
            )
        )

        if (
            "FROM DOCUMENTS"
            in upper
            and upper.startswith(
                "SELECT"
            )
        ):
            document_id = str(
                parameters[0]
            )

            chat_id = int(
                parameters[1]
            )

            self.current_row = (
                self.owner
                .documents
                .get(
                    (
                        document_id,
                        chat_id,
                    )
                )
            )

            return self

        if upper.startswith(
            "DELETE FROM PUBLIC.RAG_CHUNKS"
        ):
            self.owner.begin_write()

            (
                collection_name,
                chat_id,
                document_id,
            ) = parameters

            matching_keys = [
                key
                for key, value
                in self.owner
                .rag_rows.items()
                if (
                    value[
                        "collection_name"
                    ]
                    == collection_name
                    and value[
                        "chat_id"
                    ]
                    == chat_id
                    and value[
                        "document_id"
                    ]
                    == document_id
                )
            ]

            for key in matching_keys:
                del self.owner.rag_rows[
                    key
                ]

            self.rowcount = len(
                matching_keys
            )

            return self

        if upper.startswith(
            "INSERT INTO PUBLIC.RAG_CHUNKS"
        ):
            self.owner.begin_write()

            self.owner.insert_count += 1

            if (
                self.owner
                .fail_on_insert
                == self.owner
                .insert_count
            ):
                raise RuntimeError(
                    "postgresql://"
                    "user:private-secret@"
                    "host/database"
                )

            (
                chunk_id,
                collection_name,
                chat_id,
                document_id,
                filename,
                page,
                chunk_index,
                content,
                embedding,
                created_at,
            ) = parameters

            self.owner.rag_rows[
                chunk_id
            ] = {
                "collection_name": (
                    collection_name
                ),
                "chat_id": chat_id,
                "document_id": (
                    document_id
                ),
                "filename": filename,
                "page": page,
                "chunk_index": (
                    chunk_index
                ),
                "content": content,
                "embedding": embedding,
                "created_at": (
                    created_at
                ),
            }

            self.rowcount = 1

            return self

        return self

    def fetchone(self):
        return self.current_row

    def close(self):
        self.closed = True


class FakeTargetConnection:
    def __init__(
        self,
        plan,
        *,
        fail_on_insert=None,
    ):
        self.documents = {
            (
                target.document_id,
                target.chat_id,
            ): (
                target.document_id,
                target.chat_id,
                target.filename,
                target.file_hash,
                target.page_count,
                target.chunk_count,
                "ready",
            )
            for target in plan.targets
        }

        self.fail_on_insert = (
            fail_on_insert
        )

        self.insert_count = 0
        self.statements = []
        self.rag_rows = {}
        self.snapshot = None
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return FakeTargetCursor(
            self
        )

    def begin_write(self):
        if self.snapshot is None:
            self.snapshot = dict(
                self.rag_rows
            )

    def commit(self):
        self.committed = True
        self.snapshot = None

    def rollback(self):
        self.rolled_back = True

        if self.snapshot is not None:
            self.rag_rows = dict(
                self.snapshot
            )

        self.snapshot = None


class LegacyRAGMigrationTests(
    unittest.TestCase
):
    def build_plan(
        self,
        *,
        mismatched_hash=False,
        divergent=False,
    ):
        temporary = (
            tempfile
            .TemporaryDirectory()
        )

        root = Path(
            temporary.name
        )

        database_path = (
            root / "chat.db"
        )

        create_source_database(
            database_path,
            mismatched_hash=(
                mismatched_hash
            ),
        )

        connection = sqlite3.connect(
            database_path
        )

        try:
            plan = (
                build_legacy_rag_plan(
                    connection,
                    FakeCollection(
                        divergent=(
                            divergent
                        )
                    ),
                    embedding_dimension=3,
                )
            )

        finally:
            connection.close()

        return temporary, plan

    def test_identical_duplicates_map_to_five_documents(
        self,
    ):
        temporary, plan = (
            self.build_plan()
        )

        self.addCleanup(
            temporary.cleanup
        )

        self.assertTrue(
            plan.can_execute
        )

        self.assertEqual(
            plan.source_record_count,
            6,
        )

        self.assertEqual(
            plan
            .distinct_source_fingerprints,
            1,
        )

        self.assertEqual(
            len(plan.targets),
            5,
        )

        self.assertEqual(
            plan
            .ignored_source_duplicates,
            5,
        )

        self.assertEqual(
            len(
                plan
                .unmatched_documents
            ),
            1,
        )

        self.assertEqual(
            plan
            .unmatched_documents[0]
            .document_id,
            "certificate-doc",
        )

    def test_mismatched_database_hash_blocks_plan(
        self,
    ):
        temporary, plan = (
            self.build_plan(
                mismatched_hash=True
            )
        )

        self.addCleanup(
            temporary.cleanup
        )

        self.assertFalse(
            plan.can_execute
        )

        self.assertGreater(
            len(plan.issues),
            0,
        )

    def test_distinct_legacy_embedding_blocks_plan(
        self,
    ):
        temporary, plan = (
            self.build_plan(
                divergent=True
            )
        )

        self.addCleanup(
            temporary.cleanup
        )

        self.assertFalse(
            plan.can_execute
        )

        self.assertGreater(
            len(plan.issues),
            0,
        )

    def test_execution_is_transactional_and_idempotent(
        self,
    ):
        temporary, plan = (
            self.build_plan()
        )

        self.addCleanup(
            temporary.cleanup
        )

        target = (
            FakeTargetConnection(
                plan
            )
        )

        first = (
            execute_legacy_rag_migration(
                plan,
                target,
                collection_name=(
                    "pdf_documents"
                ),
            )
        )

        self.assertEqual(
            first.migrated_documents,
            5,
        )

        self.assertEqual(
            len(
                target.rag_rows
            ),
            5,
        )

        second = (
            execute_legacy_rag_migration(
                plan,
                target,
                collection_name=(
                    "pdf_documents"
                ),
            )
        )

        self.assertEqual(
            second.migrated_chunks,
            5,
        )

        self.assertEqual(
            len(
                target.rag_rows
            ),
            5,
        )

        self.assertTrue(
            target.committed
        )

    def test_failure_rolls_back_all_target_rows(
        self,
    ):
        temporary, plan = (
            self.build_plan()
        )

        self.addCleanup(
            temporary.cleanup
        )

        target = (
            FakeTargetConnection(
                plan,
                fail_on_insert=2,
            )
        )

        original_rows = {
            "existing": {
                "collection_name": (
                    "pdf_documents"
                ),
                "chat_id": 999,
                "document_id": (
                    "existing-doc"
                ),
            }
        }

        target.rag_rows = dict(
            original_rows
        )

        with self.assertRaises(
            LegacyRAGMigrationError
        ) as context:
            execute_legacy_rag_migration(
                plan,
                target,
                collection_name=(
                    "pdf_documents"
                ),
            )

        self.assertTrue(
            target.rolled_back
        )

        self.assertEqual(
            target.rag_rows,
            original_rows,
        )

        self.assertNotIn(
            "private-secret",
            str(context.exception),
        )


if __name__ == "__main__":
    unittest.main()
