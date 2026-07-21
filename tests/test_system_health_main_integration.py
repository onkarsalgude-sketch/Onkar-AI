from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
)
from app.main import create_app
from app.services.system_health_service import (
    HealthCheckDefinition,
    healthy_outcome,
)


TOKEN = "v2.31-main-integration-token"

TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode(
        "utf-8"
    )
).hexdigest().upper()


def monitoring_settings(
    *,
    enabled: bool,
) -> SystemHealthMonitoringSettings:
    return SystemHealthMonitoringSettings(
        enabled=enabled,
        token_sha256=(
            TOKEN_DIGEST
            if enabled
            else ""
        ),
    )


def healthy_definitions(
    request: Request,
):
    del request

    return (
        HealthCheckDefinition(
            name="database",
            check=lambda: healthy_outcome(
                "postgresql_reachable"
            ),
            critical=True,
        ),
        HealthCheckDefinition(
            name="document_storage",
            check=lambda: healthy_outcome(
                "r2_reachable"
            ),
            critical=True,
        ),
        HealthCheckDefinition(
            name="document_recovery",
            check=lambda: healthy_outcome(
                "recovery_completed"
            ),
            critical=False,
        ),
    )


def build_application(
    *,
    enabled: bool,
):
    with (
        patch(
            "app.main.get_document_storage",
            return_value=object(),
        ),
        patch(
            "app.main.initialize_rag_runtime",
            return_value=object(),
        ),
    ):
        return create_app(
            document_recovery_runner=(
                lambda **ignored: None
            ),
            document_recovery_rag=object(),
            system_health_monitoring_settings=(
                monitoring_settings(
                    enabled=enabled
                )
            ),
            system_health_definitions_provider=(
                healthy_definitions
            ),
        )


class SystemHealthMainIntegrationTests(
    unittest.TestCase
):
    def test_disabled_monitoring_does_not_register_route(
        self,
    ):
        application = build_application(
            enabled=False
        )

        paths = application.openapi()[
            "paths"
        ]

        self.assertNotIn(
            "/admin/system-health/status",
            paths,
        )

    def test_enabled_monitoring_registers_read_only_route(
        self,
    ):
        application = build_application(
            enabled=True
        )

        route = application.openapi()[
            "paths"
        ][
            "/admin/system-health/status"
        ]

        methods = set(
            route
        )

        self.assertIn(
            "get",
            methods,
        )

        self.assertFalse(
            methods
            & {
                "post",
                "put",
                "patch",
                "delete",
            }
        )

    def test_enabled_route_requires_bearer_token(
        self,
    ):
        application = build_application(
            enabled=True
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                "/admin/system-health/status"
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

    def test_authenticated_route_returns_component_health(
        self,
    ):
        application = build_application(
            enabled=True
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                "/admin/system-health/status",
                headers={
                    "Authorization": (
                        f"Bearer {TOKEN}"
                    ),
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["service"],
            "system_health",
        )

        self.assertEqual(
            payload["status"],
            "healthy",
        )

        self.assertTrue(
            payload["ready"]
        )

        self.assertTrue(
            payload["healthy"]
        )

        self.assertEqual(
            payload["component_count"],
            3,
        )

        self.assertEqual(
            [
                component["name"]
                for component in payload[
                    "components"
                ]
            ],
            [
                "database",
                "document_storage",
                "document_recovery",
            ],
        )

    def test_main_source_uses_default_health_definitions(
        self,
    ):
        source = Path(
            "app/main.py"
        ).read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "build_default_health_check_definitions",
            source,
        )

        self.assertIn(
            "document_recovery_report",
            source,
        )

        self.assertIn(
            "system_health_settings.enabled",
            source,
        )


if __name__ == "__main__":
    unittest.main()
