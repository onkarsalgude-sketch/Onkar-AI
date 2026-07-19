import unittest
from pathlib import Path

from app.config.database import (
    DatabaseConfigurationError,
    load_database_settings,
)


class DatabaseSettingsTests(unittest.TestCase):
    def test_defaults_to_sqlite(self):
        settings = load_database_settings(
            {},
            default_sqlite_path=Path("temporary/chat.db"),
        )

        self.assertEqual(settings.backend, "sqlite")
        self.assertTrue(settings.is_sqlite)
        self.assertFalse(settings.is_postgresql)
        self.assertIsNone(settings.database_url)
        self.assertEqual(
            settings.sqlite_path,
            Path("temporary/chat.db"),
        )
        self.assertFalse(settings.require_persistence)
        self.assertEqual(settings.pool_size, 5)
        self.assertEqual(settings.connect_timeout_seconds, 10)

    def test_custom_sqlite_path(self):
        settings = load_database_settings(
            {
                "SQLITE_DB_PATH": "custom/data.db",
            }
        )

        self.assertEqual(
            settings.sqlite_path,
            Path("custom/data.db"),
        )

    def test_normalizes_render_style_postgres_url(self):
        settings = load_database_settings(
            {
                "DATABASE_URL": (
                    "postgres://user:secret@example.com:5432/onkar"
                ),
                "DATABASE_REQUIRE_PERSISTENCE": "true",
            }
        )

        self.assertEqual(settings.backend, "postgresql")
        self.assertEqual(
            settings.database_url,
            "postgresql+psycopg://user:secret@example.com:5432/onkar",
        )
        self.assertEqual(
            settings.safe_target,
            "postgresql://example.com:5432/onkar",
        )
        self.assertNotIn("user", settings.safe_target)
        self.assertNotIn("secret", settings.safe_target)

    def test_accepts_psycopg_sqlalchemy_url(self):
        settings = load_database_settings(
            {
                "DATABASE_URL": (
                    "postgresql+psycopg://user:secret@db.example/onkar"
                ),
            }
        )

        self.assertTrue(settings.is_postgresql)

    def test_requires_database_name(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_URL": "postgresql://localhost/",
                }
            )

    def test_rejects_unsupported_scheme(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_URL": "mysql://localhost/onkar",
                }
            )

    def test_persistence_requirement_fails_without_postgres(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_REQUIRE_PERSISTENCE": "true",
                }
            )

    def test_rejects_invalid_boolean(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_REQUIRE_PERSISTENCE": "sometimes",
                }
            )

    def test_rejects_non_positive_pool_size(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_POOL_SIZE": "0",
                }
            )

    def test_rejects_non_positive_timeout(self):
        with self.assertRaises(DatabaseConfigurationError):
            load_database_settings(
                {
                    "DATABASE_CONNECT_TIMEOUT": "-1",
                }
            )


if __name__ == "__main__":
    unittest.main()
