import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.pool import NullPool, QueuePool

from app.config.database import load_database_settings
from app.database.engine import build_database_engine


class DatabaseEngineTests(unittest.TestCase):
    def test_sqlite_engine_uses_existing_local_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "nested"
                / "chat_history.db"
            )

            settings = load_database_settings(
                {},
                default_sqlite_path=database_path,
            )

            engine = build_database_engine(settings)

            try:
                self.assertEqual(
                    engine.url.drivername,
                    "sqlite",
                )
                self.assertIsInstance(
                    engine.pool,
                    NullPool,
                )

                with engine.connect() as connection:
                    foreign_keys = connection.execute(
                        text("PRAGMA foreign_keys")
                    ).scalar_one()

                    busy_timeout = connection.execute(
                        text("PRAGMA busy_timeout")
                    ).scalar_one()

                self.assertEqual(foreign_keys, 1)
                self.assertEqual(busy_timeout, 10000)
                self.assertTrue(database_path.exists())
            finally:
                engine.dispose()

    def test_postgresql_engine_uses_psycopg(self):
        settings = load_database_settings(
            {
                "DATABASE_URL": (
                    "postgres://user:secret@"
                    "db.example.com:5432/onkar"
                ),
                "DATABASE_POOL_SIZE": "3",
                "DATABASE_CONNECT_TIMEOUT": "7",
            }
        )

        engine = build_database_engine(settings)

        try:
            self.assertEqual(
                engine.url.drivername,
                "postgresql+psycopg",
            )
            self.assertIsInstance(
                engine.pool,
                QueuePool,
            )
            self.assertEqual(engine.pool.size(), 3)
            self.assertEqual(
                engine.pool._max_overflow,
                0,
            )
        finally:
            engine.dispose()

    def test_engine_construction_does_not_connect(self):
        settings = load_database_settings(
            {
                "DATABASE_URL": (
                    "postgresql://user:secret@"
                    "unreachable.invalid:5432/onkar"
                ),
            }
        )

        engine = build_database_engine(settings)

        try:
            self.assertEqual(
                engine.url.drivername,
                "postgresql+psycopg",
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
