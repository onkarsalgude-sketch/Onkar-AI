import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.memory.memory as memory
from app.memory.memory import (
    MemoryPersistenceError,
)
from app.services.memory_migration_service import (
    MemoryMigrationError,
    build_memory_migration_plan,
    execute_memory_migration,
)


def create_source_memory(
    path: Path,
) -> None:
    connection = sqlite3.connect(
        path
    )

    connection.execute(
        """
        CREATE TABLE memory (
            id INTEGER PRIMARY KEY,
            role TEXT,
            content TEXT
        )
        """
    )

    records = [
        (
            index,
            (
                "user"
                if index % 2
                else "assistant"
            ),
            f"content-{index}",
        )
        for index in range(
            1,
            13,
        )
    ]

    connection.executemany(
        """
        INSERT INTO memory
        (id, role, content)
        VALUES (?, ?, ?)
        """,
        records,
    )

    connection.commit()
    connection.close()


class FakeCursor:
    def __init__(
        self,
        owner,
    ):
        self.owner = owner
        self.current_rows = []

    def execute(
        self,
        sql,
        parameters=(),
    ):
        normalized = " ".join(
            str(sql).split()
        )

        upper = normalized.upper()

        if upper.startswith(
            "CREATE TABLE"
        ):
            return self

        if upper.startswith(
            "CREATE INDEX"
        ):
            return self

        if upper.startswith(
            "INSERT INTO PUBLIC.MEMORY"
        ):
            self.owner.begin_write()

            self.owner.insert_number += 1

            if (
                self.owner.fail_on_insert
                == self.owner.insert_number
            ):
                raise RuntimeError(
                    "postgresql://"
                    "user:secret-value@"
                    "host/database"
                )

            role = str(
                parameters[0]
            )

            content = str(
                parameters[1]
            )

            source_id = int(
                parameters[2]
            )

            self.owner.rows[
                source_id
            ] = (
                role,
                content,
            )

            return self

        if (
            upper.startswith(
                "SELECT ROLE, CONTENT"
            )
            and "LEGACY_SOURCE_ID" in upper
        ):
            source_id = int(
                parameters[0]
            )

            row = self.owner.rows.get(
                source_id
            )

            self.current_rows = (
                [row]
                if row is not None
                else []
            )

            return self

        self.current_rows = []

        return self

    def fetchone(self):
        if not self.current_rows:
            return None

        return self.current_rows[0]

    def fetchall(self):
        return list(
            self.current_rows
        )

    def close(self):
        return None


class FakeConnection:
    def __init__(
        self,
        *,
        fail_on_insert=None,
    ):
        self.rows = {}
        self.snapshot = None
        self.fail_on_insert = (
            fail_on_insert
        )
        self.insert_number = 0
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return FakeCursor(
            self
        )

    def begin_write(self):
        if self.snapshot is None:
            self.snapshot = dict(
                self.rows
            )

    def commit(self):
        self.commit_count += 1
        self.snapshot = None

    def rollback(self):
        self.rollback_count += 1

        if self.snapshot is not None:
            self.rows = dict(
                self.snapshot
            )

        self.snapshot = None

    def close(self):
        return None


class MemoryPersistenceTests(
    unittest.TestCase
):
    def test_local_memory_contract_is_preserved(
        self,
    ):
        temporary = (
            tempfile
            .TemporaryDirectory()
        )

        self.addCleanup(
            temporary.cleanup
        )

        database_path = (
            Path(temporary.name)
            / "memory.db"
        )

        with patch.object(
            memory,
            "MEMORY_DB",
            database_path,
        ):
            memory.init_memory(
                environ={}
            )

            memory.add(
                "user",
                "one",
                environ={},
            )

            memory.add(
                "assistant",
                "two",
                environ={},
            )

            memory.add(
                "user",
                "three",
                environ={},
            )

            result = memory.get(
                limit=2,
                environ={},
            )

            self.assertEqual(
                result,
                [
                    {
                        "role": "assistant",
                        "content": "two",
                    },
                    {
                        "role": "user",
                        "content": "three",
                    },
                ],
            )

            memory.clear(
                environ={}
            )

            self.assertEqual(
                memory.get(
                    environ={}
                ),
                [],
            )

    def test_invalid_memory_values_are_rejected(
        self,
    ):
        with self.assertRaises(
            MemoryPersistenceError
        ):
            memory.add(
                "",
                "content",
                environ={},
            )

        with self.assertRaises(
            MemoryPersistenceError
        ):
            memory.get(
                limit=0,
                environ={},
            )

    def build_plan(self):
        temporary = (
            tempfile
            .TemporaryDirectory()
        )

        database_path = (
            Path(temporary.name)
            / "memory.db"
        )

        create_source_memory(
            database_path
        )

        connection = sqlite3.connect(
            database_path
        )

        try:
            plan = (
                build_memory_migration_plan(
                    connection
                )
            )

        finally:
            connection.close()

        return temporary, plan

    def test_migration_plan_contains_twelve_records(
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
            len(plan.records),
            12,
        )

        self.assertEqual(
            dict(plan.role_counts),
            {
                "assistant": 6,
                "user": 6,
            },
        )

    def test_migration_is_idempotent(
        self,
    ):
        temporary, plan = (
            self.build_plan()
        )

        self.addCleanup(
            temporary.cleanup
        )

        target = FakeConnection()

        first = (
            execute_memory_migration(
                plan,
                target,
            )
        )

        second = (
            execute_memory_migration(
                plan,
                target,
            )
        )

        self.assertEqual(
            first.migrated_records,
            12,
        )

        self.assertEqual(
            second.migrated_records,
            12,
        )

        self.assertEqual(
            len(target.rows),
            12,
        )

    def test_migration_failure_rolls_back(
        self,
    ):
        temporary, plan = (
            self.build_plan()
        )

        self.addCleanup(
            temporary.cleanup
        )

        target = FakeConnection(
            fail_on_insert=2
        )

        target.rows = {
            999: (
                "user",
                "existing",
            )
        }

        original_rows = dict(
            target.rows
        )

        with self.assertRaises(
            MemoryMigrationError
        ) as context:
            execute_memory_migration(
                plan,
                target,
            )

        self.assertGreater(
            target.rollback_count,
            0,
        )

        self.assertEqual(
            target.rows,
            original_rows,
        )

        self.assertNotIn(
            "secret-value",
            str(context.exception),
        )


if __name__ == "__main__":
    unittest.main()
