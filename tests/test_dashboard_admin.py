import hashlib
import unittest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dashboard_admin import (
    DASHBOARD_SUMMARY_PATH,
    create_dashboard_admin_router,
)
from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
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


def build_client(
    summary_provider,
):
    application = FastAPI()
    application.include_router(
        create_dashboard_admin_router(
            monitoring_settings(),
            summary_provider=(
                summary_provider
            ),
            db_path="dashboard-test.db",
        )
    )
    return TestClient(
        application
    )


class DashboardAdminTests(
    unittest.TestCase
):
    def test_summary_requires_bearer_token(self):
        provider = MagicMock(
            return_value={}
        )

        with build_client(
            provider
        ) as client:
            response = client.get(
                DASHBOARD_SUMMARY_PATH
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
        provider.assert_not_called()

    def test_summary_returns_authenticated_payload(self):
        summary = {
            "usage": {
                "chats": {
                    "total": 3,
                },
            },
            "recovery": {
                "available": True,
                "metrics": {
                    "total_runs": 2,
                },
            },
            "incidents": {
                "available": True,
                "metrics": {
                    "active_count": 1,
                },
            },
        }
        provider = MagicMock(
            return_value=summary
        )

        with build_client(
            provider
        ) as client:
            response = client.get(
                DASHBOARD_SUMMARY_PATH,
                headers=(
                    authorization_headers()
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.json(),
            {
                "service": "dashboard",
                "summary": summary,
            },
        )
        provider.assert_called_once_with(
            db_path="dashboard-test.db"
        )

    def test_provider_failure_is_sanitized(self):
        provider = MagicMock(
            side_effect=RuntimeError(
                "secret database path"
            )
        )

        with build_client(
            provider
        ) as client:
            response = client.get(
                DASHBOARD_SUMMARY_PATH,
                headers=(
                    authorization_headers()
                ),
            )

        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Dashboard summary "
                    "is unavailable."
                ),
            },
        )
        self.assertNotIn(
            "secret database path",
            response.text,
        )

    def test_invalid_provider_payload_is_sanitized(self):
        provider = MagicMock(
            return_value=[]
        )

        with build_client(
            provider
        ) as client:
            response = client.get(
                DASHBOARD_SUMMARY_PATH,
                headers=(
                    authorization_headers()
                ),
            )

        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertEqual(
            response.json()["detail"],
            "Dashboard summary is unavailable.",
        )

    def test_openapi_contract_is_admin_read_only(self):
        provider = MagicMock(
            return_value={}
        )

        with build_client(
            provider
        ) as client:
            schema = client.get(
                "/openapi.json"
            ).json()

        operation = schema[
            "paths"
        ][
            DASHBOARD_SUMMARY_PATH
        ][
            "get"
        ]

        self.assertEqual(
            operation["operationId"],
            "get_admin_dashboard_summary",
        )
        self.assertIn(
            "admin",
            operation["tags"],
        )
        self.assertEqual(
            set(
                schema["paths"][
                    DASHBOARD_SUMMARY_PATH
                ].keys()
            ),
            {"get"},
        )


if __name__ == "__main__":
    unittest.main()
