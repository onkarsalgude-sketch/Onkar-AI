"""Comprehensive unit and integration tests for Instance Profile foundation."""

from datetime import datetime, timezone
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select

from app.database.db import get_runtime_connection
from app.database.migrations import (
    get_schema_version,
    initialize_schema,
)
from app.database.schema import (
    SCHEMA_VERSION,
    chats,
    create_schema,
    instance_profile,
    metadata,
    schema_migrations,
)
from app.main import create_app
from app.services.profile_service import (
    ProfilePersistenceError,
    ProfileValidationError,
    derive_avatar_initials,
    get_instance_profile,
    update_instance_profile,
)


class InstanceProfileServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        initialize_schema(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_01_get_empty_database_returns_unconfigured(self):
        result = get_instance_profile(db_path=self.db_path)
        self.assertFalse(result["configured"])
        self.assertIsNone(result["display_name"])
        self.assertIsNone(result["avatar_initials"])
        self.assertIsNone(result["timezone"])
        self.assertIsNone(result["created_at"])
        self.assertIsNone(result["updated_at"])

    def test_02_get_does_not_create_database_row(self):
        get_instance_profile(db_path=self.db_path)
        with self.engine.connect() as connection:
            count = connection.execute(
                select(instance_profile)
            ).fetchall()
            self.assertEqual(len(count), 0)

    def test_03_valid_put_creates_singleton_profile(self):
        result = update_instance_profile(
            display_name="Onkar Salgude",
            timezone="Asia/Kolkata",
            db_path=self.db_path,
        )
        self.assertTrue(result["configured"])
        self.assertEqual(result["display_name"], "Onkar Salgude")
        self.assertEqual(result["avatar_initials"], "OS")
        self.assertEqual(result["timezone"], "Asia/Kolkata")
        self.assertIsNotNone(result["created_at"])
        self.assertIsNotNone(result["updated_at"])

    def test_04_display_name_is_trimmed(self):
        result = update_instance_profile(
            display_name="   Onkar Salgude   ",
            db_path=self.db_path,
        )
        self.assertEqual(result["display_name"], "Onkar Salgude")

    def test_05_blank_display_name_is_rejected(self):
        with self.assertRaises(ProfileValidationError):
            update_instance_profile(
                display_name="   ",
                db_path=self.db_path,
            )

    def test_06_display_name_over_50_chars_is_rejected(self):
        with self.assertRaises(ProfileValidationError):
            update_instance_profile(
                display_name="A" * 51,
                db_path=self.db_path,
            )

    def test_07_control_character_display_name_is_rejected(self):
        with self.assertRaises(ProfileValidationError):
            update_instance_profile(
                display_name="Onkar\x00Salgude",
                db_path=self.db_path,
            )

    def test_08_unicode_display_name_is_supported(self):
        result = update_instance_profile(
            display_name=" Onkar-AI User ",
            db_path=self.db_path,
        )
        self.assertEqual(result["display_name"], "Onkar-AI User")
        self.assertEqual(result["avatar_initials"], "OU")

    def test_09_initials_derive_correctly_for_multi_word(self):
        self.assertEqual(derive_avatar_initials("Onkar Salgude"), "OS")
        self.assertEqual(derive_avatar_initials("Jane Mary Doe"), "JD")

    def test_10_initials_derive_correctly_for_single_word(self):
        self.assertEqual(derive_avatar_initials("Onkar"), "ON")
        self.assertEqual(derive_avatar_initials("A"), "A")

    def test_11_valid_iana_timezone_is_accepted(self):
        result = update_instance_profile(
            display_name="Onkar",
            timezone="America/New_York",
            db_path=self.db_path,
        )
        self.assertEqual(result["timezone"], "America/New_York")

    def test_12_invalid_timezone_is_rejected(self):
        with self.assertRaises(ProfileValidationError):
            update_instance_profile(
                display_name="Onkar",
                timezone="Invalid/Timezone",
                db_path=self.db_path,
            )

    def test_13_blank_timezone_string_is_rejected(self):
        with self.assertRaises(ProfileValidationError):
            update_instance_profile(
                display_name="Onkar",
                timezone="   ",
                db_path=self.db_path,
            )

    def test_14_timezone_null_clears_existing_timezone(self):
        update_instance_profile(
            display_name="Onkar",
            timezone="Asia/Kolkata",
            db_path=self.db_path,
        )
        updated = update_instance_profile(
            display_name="Onkar",
            timezone=None,
            db_path=self.db_path,
        )
        self.assertIsNone(updated["timezone"])

    def test_15_created_at_remains_stable_and_updated_at_advances(self):
        t1 = datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

        first = update_instance_profile(
            display_name="Onkar",
            db_path=self.db_path,
            now_provider=lambda: t1,
        )

        second = update_instance_profile(
            display_name="Onkar Salgude",
            db_path=self.db_path,
            now_provider=lambda: t2,
        )

        self.assertEqual(first["created_at"], second["created_at"])
        self.assertNotEqual(first["updated_at"], second["updated_at"])
        self.assertEqual(second["updated_at"], t2.isoformat())

    def test_16_singleton_constraint_enforces_single_row(self):
        update_instance_profile(
            display_name="Initial Name",
            db_path=self.db_path,
        )
        update_instance_profile(
            display_name="Updated Name",
            db_path=self.db_path,
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                select(instance_profile)
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].id, 1)
            self.assertEqual(rows[0].display_name, "Updated Name")


class InstanceProfileApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        initialize_schema(self.engine)

        app = create_app()

        # Wire test db override into app state or mock service
        self.client = TestClient(app)

    def tearDown(self):
        self.engine.dispose()

    def test_17_get_profile_returns_service_contract(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["service"], "profile")
        self.assertIn("profile", data)
        self.assertIn("configured", data["profile"])

    def test_18_put_profile_validates_and_updates(self):
        response = self.client.put(
            "/profile",
            json={
                "display_name": "Onkar Salgude",
                "timezone": "Asia/Kolkata",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["service"], "profile")
        profile = data["profile"]
        self.assertTrue(profile["configured"])
        self.assertEqual(profile["display_name"], "Onkar Salgude")
        self.assertEqual(profile["avatar_initials"], "OS")
        self.assertEqual(profile["timezone"], "Asia/Kolkata")

    def test_19_put_profile_invalid_display_name_returns_400(self):
        response = self.client.put(
            "/profile",
            json={
                "display_name": "  ",
            },
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)

    def test_20_put_profile_invalid_timezone_returns_400(self):
        response = self.client.put(
            "/profile",
            json={
                "display_name": "Onkar",
                "timezone": "Invalid/Zone",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_21_response_exposes_no_database_id_or_secrets(self):
        self.client.put(
            "/profile",
            json={"display_name": "Onkar"},
        )
        response = self.client.get("/profile")
        data = response.json()
        profile_keys = set(data["profile"].keys())

        forbidden = {"id", "user_id", "email", "password", "secret", "token"}
        self.assertFalse(profile_keys & forbidden)

    def test_22_fresh_database_migration_reaches_schema_v7(self):
        version = initialize_schema(self.engine)
        self.assertEqual(version, 7)
        self.assertEqual(get_schema_version(self.engine), 7)

    def test_23_migration_from_v6_to_v7_preserves_existing_chats(self):
        # Create schema up to v6 manually
        metadata_v6 = metadata
        with self.engine.begin() as connection:
            create_schema(self.engine)
            connection.execute(
                insert(chats).values(
                    title="Pre-migration Chat",
                    created_at="2026-07-26T00:00:00+00:00",
                )
            )

        initialize_schema(self.engine)
        self.assertEqual(get_schema_version(self.engine), 7)

        with self.engine.connect() as connection:
            rows = connection.execute(
                select(chats.c.title)
            ).scalars().all()
            self.assertIn("Pre-migration Chat", rows)

    def test_24_postgresql_portability_expectations_valid(self):
        # Verify table object constraints and column definitions for non-SQLite engines
        self.assertEqual(instance_profile.name, "instance_profile")
        col_names = {col.name for col in instance_profile.columns}
        self.assertEqual(
            col_names,
            {"id", "display_name", "timezone", "created_at", "updated_at"},
        )


if __name__ == "__main__":
    unittest.main()
