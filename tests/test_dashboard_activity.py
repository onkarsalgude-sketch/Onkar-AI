import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient

from app.api.dashboard_admin import (
    DASHBOARD_ACTIVITY_TODAY_PATH,
    create_dashboard_admin_router,
)
from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
)
from app.services.dashboard_service import (
    DashboardMetricsError,
    summarize_today_conversation_activity,
)


TOKEN = "v2.37-dashboard-token"
TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode("utf-8")
).hexdigest()


def monitoring_settings():
    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=TOKEN_DIGEST,
    )


def authorization_headers():
    return {
        "Authorization": (
            f"Bearer {TOKEN}"
        )
    }


class DashboardActivityTests(
    unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = (
            Path(
                self.temporary_directory.name
            )
            / "activity.db"
        )
        self._create_database()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def connection_factory(
        self,
        db_path,
    ):
        return sqlite3.connect(
            str(db_path)
        )

    def _create_database(self):
        connection = sqlite3.connect(
            str(self.database_path)
        )
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL DEFAULT 1,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
        connection.close()

    def _insert_message(
        self,
        message_id,
        role,
        created_at,
    ):
        connection = sqlite3.connect(
            str(self.database_path)
        )
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO messages (
                id,
                chat_id,
                role,
                content,
                created_at
            )
            VALUES (?, 1, ?, 'test', ?)
            """,
            (
                message_id,
                role,
                created_at,
            ),
        )
        connection.commit()
        connection.close()

    def test_1_empty_day_returns_zero_counts_and_six_buckets(
        self,
    ):
        fixed_now = lambda: datetime(
            2026, 7, 26, 12, 0, 0
        )
        activity = (
            summarize_today_conversation_activity(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
                now_provider=fixed_now,
            )
        )
        self.assertEqual(
            activity["scope"],
            "conversation activity",
        )
        self.assertEqual(
            activity["day"],
            "2026-07-26",
        )
        self.assertEqual(
            activity["day_basis"],
            "server-local calendar day",
        )
        self.assertEqual(
            activity["start"],
            "2026-07-26T00:00:00",
        )
        self.assertEqual(
            activity["end_exclusive"],
            "2026-07-27T00:00:00",
        )
        self.assertEqual(
            activity["bucket_hours"],
            4,
        )
        self.assertEqual(
            activity["messages"],
            {
                "total": 0,
                "user": 0,
                "assistant": 0,
                "other": 0,
            },
        )
        self.assertEqual(
            len(activity["buckets"]),
            6,
        )
        for bucket in activity[
            "buckets"
        ]:
            self.assertEqual(
                bucket["message_count"],
                0,
            )

    def test_2_day_boundaries_are_half_open(
        self,
    ):
        fixed_now = lambda: datetime(
            2026, 7, 26, 12, 0, 0
        )
        self._insert_message(
            1,
            "user",
            "2026-07-25T23:59:59.999999",
        )
        self._insert_message(
            2,
            "user",
            "2026-07-26T00:00:00",
        )
        self._insert_message(
            3,
            "user",
            "2026-07-26T23:59:59.999999",
        )
        self._insert_message(
            4,
            "user",
            "2026-07-27T00:00:00",
        )

        activity = (
            summarize_today_conversation_activity(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
                now_provider=fixed_now,
            )
        )
        self.assertEqual(
            activity["messages"]["total"],
            2,
        )

    def test_3_user_assistant_other_counts_reconcile_correctly(
        self,
    ):
        fixed_now = lambda: datetime(
            2026, 7, 26, 10, 0, 0
        )
        self._insert_message(
            1,
            "user",
            "2026-07-26T01:00:00",
        )
        self._insert_message(
            2,
            "user",
            "2026-07-26T02:00:00",
        )
        self._insert_message(
            3,
            "assistant",
            "2026-07-26T03:00:00",
        )
        self._insert_message(
            4,
            "system",
            "2026-07-26T04:00:00",
        )
        self._insert_message(
            5,
            "tool",
            "2026-07-26T05:00:00",
        )

        activity = (
            summarize_today_conversation_activity(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
                now_provider=fixed_now,
            )
        )
        msg = activity["messages"]
        self.assertEqual(
            msg["user"],
            2,
        )
        self.assertEqual(
            msg["assistant"],
            1,
        )
        self.assertEqual(
            msg["other"],
            2,
        )
        self.assertEqual(
            msg["total"],
            msg["user"]
            + msg["assistant"]
            + msg["other"],
        )

    def test_4_four_hour_bucket_counts_come_from_real_timestamps(
        self,
    ):
        fixed_now = lambda: datetime(
            2026, 7, 26, 12, 0, 0
        )
        self._insert_message(
            1,
            "user",
            "2026-07-26T01:30:00",
        )
        self._insert_message(
            2,
            "user",
            "2026-07-26T04:00:00",
        )
        self._insert_message(
            3,
            "assistant",
            "2026-07-26T07:59:59",
        )
        self._insert_message(
            4,
            "user",
            "2026-07-26T15:00:00",
        )
        self._insert_message(
            5,
            "assistant",
            "2026-07-26T22:00:00",
        )

        activity = (
            summarize_today_conversation_activity(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
                now_provider=fixed_now,
            )
        )
        counts = [
            b["message_count"]
            for b in activity["buckets"]
        ]
        self.assertEqual(
            counts,
            [1, 2, 0, 1, 0, 1],
        )
        self.assertEqual(
            sum(counts),
            activity["messages"][
                "total"
            ],
        )

    def test_5_invalid_clock_fails_generically(
        self,
    ):
        def bad_clock():
            raise RuntimeError(
                "Clock out of sync"
            )

        with self.assertRaises(
            DashboardMetricsError
        ) as ctx:
            summarize_today_conversation_activity(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    self.connection_factory
                ),
                now_provider=bad_clock,
            )
        self.assertEqual(
            str(ctx.exception),
            "Dashboard activity is unavailable.",
        )

    def test_6_database_failures_do_not_leak_internal_details(
        self,
    ):
        bad_factory = lambda path: sqlite3.connect(
            "nonexistent_directory/invalid.db"
        )

        with self.assertRaises(
            DashboardMetricsError
        ) as ctx:
            summarize_today_conversation_activity(
                db_path="invalid.db",
                connection_factory=bad_factory,
                now_provider=lambda: datetime(
                    2026, 7, 26, 12, 0, 0
                ),
            )
        self.assertEqual(
            str(ctx.exception),
            "Dashboard activity is unavailable.",
        )
        self.assertNotIn(
            "nonexistent_directory",
            str(ctx.exception),
        )

    def test_7_route_path_is_exactly_admin_dashboard_activity_today(
        self,
    ):
        self.assertEqual(
            DASHBOARD_ACTIVITY_TODAY_PATH,
            "/admin/dashboard/activity/today",
        )

    def test_8_missing_dashboard_bearer_returns_401(
        self,
    ):
        application = FastAPI()
        application.include_router(
            create_dashboard_admin_router(
                monitoring_settings(),
                activity_provider=lambda db_path=None: {},
            )
        )
        client = TestClient(
            application
        )
        response = client.get(
            DASHBOARD_ACTIVITY_TODAY_PATH
        )
        self.assertEqual(
            response.status_code,
            401,
        )
        self.assertEqual(
            response.headers.get(
                "www-authenticate"
            ),
            "Bearer",
        )

    def test_9_authenticated_request_returns_dashboard_activity_payload(
        self,
    ):
        sample_activity = {
            "scope": "conversation activity",
            "day": "2026-07-26",
            "day_basis": "server-local calendar day",
            "start": (
                "2026-07-26T00:00:00"
            ),
            "end_exclusive": (
                "2026-07-27T00:00:00"
            ),
            "bucket_hours": 4,
            "messages": {
                "total": 0,
                "user": 0,
                "assistant": 0,
                "other": 0,
            },
            "buckets": [],
        }
        activity_provider = MagicMock(
            return_value=sample_activity
        )
        application = FastAPI()
        application.include_router(
            create_dashboard_admin_router(
                monitoring_settings(),
                activity_provider=activity_provider,
            )
        )
        client = TestClient(
            application
        )
        response = client.get(
            DASHBOARD_ACTIVITY_TODAY_PATH,
            headers=authorization_headers(),
        )
        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.json(),
            {
                "service": "dashboard_activity",
                "activity": sample_activity,
            },
        )

    def test_10_provider_failure_returns_generic_503(
        self,
    ):
        def failing_provider(
            db_path=None,
        ):
            raise DashboardMetricsError(
                "Dashboard activity is unavailable."
            )

        application = FastAPI()
        application.include_router(
            create_dashboard_admin_router(
                monitoring_settings(),
                activity_provider=failing_provider,
            )
        )
        client = TestClient(
            application
        )
        response = client.get(
            DASHBOARD_ACTIVITY_TODAY_PATH,
            headers=authorization_headers(),
        )
        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Dashboard activity is unavailable."
                )
            },
        )
