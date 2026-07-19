import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database.db import (
    PortableConnection,
    PortableRow,
    _convert_qmark_placeholders,
    get_runtime_connection,
)


class FakeCursor:
    def __init__(self):
        self.executed_sql = None
        self.executed_parameters = None
        self.description = (
            ("id", None, None, None, None, None, None),
            ("title", None, None, None, None, None, None),
        )
        self.rowcount = 1
        self.lastrowid = None
        self._rows = [
            (7, "Portable row"),
        ]

    def execute(
        self,
        sql,
        parameters=None,
    ):
        self.executed_sql = sql
        self.executed_parameters = parameters

    def executemany(
        self,
        sql,
        parameter_sets,
    ):
        self.executed_sql = sql
        self.executed_parameters = list(
            parameter_sets
        )

    def fetchone(self):
        if not self._rows:
            return None

        return self._rows.pop(0)

    def fetchmany(self, size=1):
        rows = self._rows[:size]
        self._rows = self._rows[size:]
        return rows

    def fetchall(self):
        rows = list(self._rows)
        self._rows.clear()
        return rows

    def close(self):
        return None

    def __iter__(self):
        return iter(self._rows)


class FakeRawConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self):
        self.raw = FakeRawConnection()

    def raw_connection(self):
        return self.raw


class DatabaseAdapterTests(unittest.TestCase):
    def test_qmark_conversion_ignores_literals_and_comments(
        self,
    ):
        sql = (
            "SELECT '?' AS literal "
            "FROM messages "
            "WHERE id = ? "
            "AND content = 'That''s ?' "
            "-- ignored ?\n"
            "AND role = ? "
            "/* ignored ? */"
        )

        converted = (
            _convert_qmark_placeholders(sql)
        )

        self.assertEqual(
            converted.count("%s"),
            2,
        )
        self.assertIn(
            "'?' AS literal",
            converted,
        )
        self.assertIn(
            "'That''s ?'",
            converted,
        )
        self.assertIn(
            "-- ignored ?",
            converted,
        )
        self.assertIn(
            "/* ignored ? */",
            converted,
        )

    def test_sqlite_runtime_connection_remains_native(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            db_path = (
                Path(directory)
                / "runtime.db"
            )

            connection = get_runtime_connection(
                str(db_path),
                environ={},
            )

            try:
                self.assertIsInstance(
                    connection,
                    sqlite3.Connection,
                )

                cursor = connection.cursor()
                cursor.execute(
                    """
                    CREATE TABLE items (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO items (
                        id,
                        name
                    )
                    VALUES (?, ?)
                    """,
                    (1, "SQLite"),
                )
                connection.commit()

                cursor.execute(
                    """
                    SELECT name
                    FROM items
                    WHERE id = ?
                    """,
                    (1,),
                )

                self.assertEqual(
                    cursor.fetchone()[0],
                    "SQLite",
                )
            finally:
                connection.close()

    def test_portable_cursor_converts_qmark_parameters(
        self,
    ):
        raw = FakeRawConnection()
        connection = PortableConnection(raw)
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id, title
            FROM chats
            WHERE id = ?
            """,
            (7,),
        )

        self.assertIn(
            "WHERE id = %s",
            raw.cursor_instance.executed_sql,
        )
        self.assertEqual(
            raw.cursor_instance.executed_parameters,
            (7,),
        )

    def test_row_factory_supports_name_and_position_access(
        self,
    ):
        raw = FakeRawConnection()
        connection = PortableConnection(raw)
        connection.row_factory = object()

        row = connection.execute(
            "SELECT id, title FROM chats"
        ).fetchone()

        self.assertIsInstance(
            row,
            PortableRow,
        )
        self.assertEqual(row[0], 7)
        self.assertEqual(
            row["title"],
            "Portable row",
        )

    def test_postgresql_runtime_uses_portable_connection(
        self,
    ):
        fake_engine = FakeEngine()

        with patch(
            "app.database.db._get_runtime_engine",
            return_value=fake_engine,
        ):
            connection = get_runtime_connection(
                environ={
                    "DATABASE_URL": (
                        "postgres://user:secret@"
                        "db.example.com:5432/onkar"
                    ),
                }
            )

        self.assertIsInstance(
            connection,
            PortableConnection,
        )

        connection.execute(
            "SELECT id FROM chats WHERE id = ?",
            (1,),
        )

        self.assertIn(
            "%s",
            fake_engine.raw.cursor_instance.executed_sql,
        )

    def test_context_manager_commits_and_closes(
        self,
    ):
        raw = FakeRawConnection()

        with PortableConnection(raw):
            pass

        self.assertTrue(raw.committed)
        self.assertTrue(raw.closed)


if __name__ == "__main__":
    unittest.main()
