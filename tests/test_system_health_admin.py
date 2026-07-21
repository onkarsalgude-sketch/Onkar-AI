from __future__ import annotations

import hashlib
import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.system_health_admin import (
    SYSTEM_HEALTH_STATUS_PATH,
    create_system_health_admin_router,
)
from app.config.system_health_monitoring import (
    DEFAULT_SYSTEM_HEALTH_STATUS_ENABLED,
    SystemHealthMonitoringConfigurationError,
    SystemHealthMonitoringSettings,
    load_system_health_monitoring_settings,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    healthy_outcome,
)


TOKEN = "v2.31-system-health-monitoring-token"

TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode(
        "utf-8"
    )
).hexdigest()


def enabled_settings(
    *,
    uppercase_digest: bool = False,
) -> SystemHealthMonitoringSettings:
    digest = (
        TOKEN_DIGEST.upper()
        if uppercase_digest
        else TOKEN_DIGEST
    )

    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=digest,
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
    )


def build_application(
    *,
    settings: SystemHealthMonitoringSettings | None = None,
    definitions_provider=healthy_definitions,
) -> FastAPI:
    application = FastAPI()

    application.include_router(
        create_system_health_admin_router(
            settings or enabled_settings(),
            definitions_provider=(
                definitions_provider
            ),
        )
    )

    return application


class SystemHealthMonitoringConfigurationTests(
    unittest.TestCase
):
    def test_default_configuration_is_disabled(
        self,
    ):
        settings = (
            load_system_health_monitoring_settings(
                {}
            )
        )

        self.assertEqual(
            settings.enabled,
            DEFAULT_SYSTEM_HEALTH_STATUS_ENABLED,
        )

        self.assertFalse(
            settings.enabled
        )

        self.assertEqual(
            settings.token_sha256,
            "",
        )

    def test_enabled_configuration_normalizes_digest(
        self,
    ):
        settings = (
            load_system_health_monitoring_settings(
                {
                    "SYSTEM_HEALTH_STATUS_ENABLED": (
                        "true"
                    ),
                    "SYSTEM_HEALTH_STATUS_TOKEN_SHA256": (
                        TOKEN_DIGEST.upper()
                    ),
                }
            )
        )

        self.assertTrue(
            settings.enabled
        )

        self.assertEqual(
            settings.token_sha256,
            TOKEN_DIGEST,
        )

    def test_invalid_boolean_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemHealthMonitoringConfigurationError
        ):
            load_system_health_monitoring_settings(
                {
                    "SYSTEM_HEALTH_STATUS_ENABLED": (
                        "sometimes"
                    ),
                }
            )

    def test_enabled_configuration_requires_digest(
        self,
    ):
        with self.assertRaises(
            SystemHealthMonitoringConfigurationError
        ):
            load_system_health_monitoring_settings(
                {
                    "SYSTEM_HEALTH_STATUS_ENABLED": (
                        "true"
                    ),
                }
            )

    def test_invalid_digest_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemHealthMonitoringConfigurationError
        ):
            load_system_health_monitoring_settings(
                {
                    "SYSTEM_HEALTH_STATUS_ENABLED": (
                        "false"
                    ),
                    "SYSTEM_HEALTH_STATUS_TOKEN_SHA256": (
                        "not-a-digest"
                    ),
                }
            )


class SystemHealthAdminApiTests(
    unittest.TestCase
):
    def test_missing_bearer_is_rejected_before_checks(
        self,
    ):
        call_count = 0

        def provider(
            request: Request,
        ):
            nonlocal call_count
            del request

            call_count += 1

            return ()

        application = build_application(
            definitions_provider=provider
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH
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

        self.assertEqual(
            call_count,
            0,
        )

    def test_wrong_bearer_is_rejected(
        self,
    ):
        application = build_application()

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
                headers={
                    "Authorization": (
                        "Bearer wrong-token"
                    ),
                },
            )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_uppercase_configured_digest_authenticates(
        self,
    ):
        application = build_application(
            settings=enabled_settings(
                uppercase_digest=True
            )
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
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

    def test_healthy_report_is_returned(
        self,
    ):
        application = build_application()

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
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
            1,
        )

        self.assertEqual(
            payload["components"][0]["name"],
            "database",
        )

    def test_failing_component_is_sanitized(
        self,
    ):
        def provider(
            request: Request,
        ):
            del request

            def failing_check():
                raise RuntimeError(
                    "postgresql://user:password@host/database"
                )

            return (
                HealthCheckDefinition(
                    name="database",
                    check=failing_check,
                    critical=True,
                ),
            )

        application = build_application(
            definitions_provider=provider
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
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
            payload["status"],
            "unhealthy",
        )

        self.assertEqual(
            payload["components"][0]["detail"],
            "check_failed",
        )

        serialized = response.text.casefold()

        self.assertNotIn(
            "password",
            serialized,
        )

        self.assertNotIn(
            "postgresql://",
            serialized,
        )

    def test_definitions_provider_failure_is_sanitized(
        self,
    ):
        def failing_provider(
            request: Request,
        ):
            del request

            raise RuntimeError(
                "R2 access key and secret"
            )

        application = build_application(
            definitions_provider=(
                failing_provider
            )
        )

        with TestClient(
            application
        ) as client:
            response = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
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
            payload["status"],
            "unhealthy",
        )

        self.assertFalse(
            payload["ready"]
        )

        self.assertEqual(
            payload["components"][0]["name"],
            "health_runtime",
        )

        self.assertEqual(
            payload["components"][0]["detail"],
            "check_failed",
        )

        self.assertNotIn(
            "access key",
            response.text.casefold(),
        )

    def test_route_is_read_only(
        self,
    ):
        application = build_application()

        path_contract = application.openapi()[
            "paths"
        ][
            SYSTEM_HEALTH_STATUS_PATH
        ]

        methods = set(
            path_contract
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


if __name__ == "__main__":
    unittest.main()
