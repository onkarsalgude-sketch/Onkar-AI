import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dashboard_admin import (
    DASHBOARD_HEALTH_PATH,
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
    health_provider=None,
):
    application = FastAPI()
    application.state.document_recovery_report = (
        SimpleNamespace(
            status="completed",
            enabled=True,
            failure_count=0,
        )
    )
    application.state.rag_runtime = (
        SimpleNamespace(
            settings=object()
        )
    )

    kwargs = {
        "summary_provider": summary_provider,
        "db_path": "dashboard-test.db",
    }

    if health_provider is not None:
        kwargs["health_provider"] = (
            health_provider
        )

    application.include_router(
        create_dashboard_admin_router(
            monitoring_settings(),
            **kwargs,
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

    def test_health_requires_bearer_token(self):
        health_provider = MagicMock(
            return_value={}
        )

        with build_client(
            MagicMock(
                return_value={}
            ),
            health_provider,
        ) as client:
            response = client.get(
                DASHBOARD_HEALTH_PATH
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
        health_provider.assert_not_called()

    def test_health_returns_authenticated_payload(self):
        health = {
            "service": "system_health",
            "status": "healthy",
            "ready": True,
            "healthy": True,
            "attention_required": False,
            "checked_at": (
                "2026-07-24T12:00:00.000Z"
            ),
            "duration_ms": 4,
            "component_count": 4,
            "components": [],
        }
        provider = MagicMock(
            return_value=health
        )

        with build_client(
            MagicMock(
                return_value={}
            ),
            provider,
        ) as client:
            recovery_report = (
                client.app.state
                .document_recovery_report
            )
            rag_runtime = (
                client.app.state.rag_runtime
            )

            response = client.get(
                DASHBOARD_HEALTH_PATH,
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
                "service": (
                    "dashboard_health"
                ),
                "health": health,
            },
        )
        provider.assert_called_once_with(
            recovery_report=(
                recovery_report
            ),
            rag_runtime=rag_runtime,
        )

    def test_health_provider_failure_is_sanitized(self):
        provider = MagicMock(
            side_effect=RuntimeError(
                "postgresql://secret"
            )
        )

        with build_client(
            MagicMock(
                return_value={}
            ),
            provider,
        ) as client:
            response = client.get(
                DASHBOARD_HEALTH_PATH,
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
                    "Dashboard health "
                    "is unavailable."
                ),
            },
        )
        self.assertNotIn(
            "postgresql://secret",
            response.text,
        )

    def test_openapi_contract_is_admin_read_only(self):
        provider = MagicMock(
            return_value={}
        )

        with build_client(
            provider,
            MagicMock(
                return_value={}
            ),
        ) as client:
            schema = client.get(
                "/openapi.json"
            ).json()

        summary_operation = schema[
            "paths"
        ][
            DASHBOARD_SUMMARY_PATH
        ][
            "get"
        ]
        health_operation = schema[
            "paths"
        ][
            DASHBOARD_HEALTH_PATH
        ][
            "get"
        ]

        self.assertEqual(
            summary_operation[
                "operationId"
            ],
            "get_admin_dashboard_summary",
        )
        self.assertEqual(
            health_operation[
                "operationId"
            ],
            "get_admin_dashboard_health",
        )
        self.assertIn(
            "admin",
            summary_operation["tags"],
        )
        self.assertIn(
            "admin",
            health_operation["tags"],
        )

        for path in (
            DASHBOARD_SUMMARY_PATH,
            DASHBOARD_HEALTH_PATH,
        ):
            self.assertEqual(
                set(
                    schema["paths"][
                        path
                    ].keys()
                ),
                {"get"},
            )


if __name__ == "__main__":
    unittest.main()
