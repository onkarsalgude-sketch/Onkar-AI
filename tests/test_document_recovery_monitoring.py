from __future__ import annotations

import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.document_recovery_admin import (
    create_document_recovery_admin_router,
)
from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.config.document_recovery_monitoring import (
    DEFAULT_DOCUMENT_RECOVERY_STATUS_ENABLED,
    DocumentRecoveryMonitoringConfigurationError,
    DocumentRecoveryMonitoringSettings,
    load_document_recovery_monitoring_settings,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
)


PLAINTEXT_TOKEN = (
    "v228-monitoring-test-token"
)

TOKEN_SHA256 = hashlib.sha256(
    PLAINTEXT_TOKEN.encode("utf-8")
).hexdigest()


def enabled_monitoring_settings(
) -> DocumentRecoveryMonitoringSettings:
    return DocumentRecoveryMonitoringSettings(
        enabled=True,
        token_sha256=TOKEN_SHA256,
    )


def authorization_headers(
    token: str = PLAINTEXT_TOKEN,
) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {token}"
        ),
    }


def monitoring_app(
    report=None,
) -> FastAPI:
    application = FastAPI()

    application.state.document_recovery_report = (
        report
    )

    application.include_router(
        create_document_recovery_admin_router(
            enabled_monitoring_settings()
        )
    )

    return application


class DocumentRecoveryMonitoringConfigurationTests(
    unittest.TestCase
):
    def test_monitoring_is_disabled_by_default(
        self,
    ):
        settings = (
            load_document_recovery_monitoring_settings(
                {}
            )
        )

        self.assertEqual(
            settings.enabled,
            DEFAULT_DOCUMENT_RECOVERY_STATUS_ENABLED,
        )

        self.assertEqual(
            settings.token_sha256,
            "",
        )

    def test_enabled_monitoring_loads_normalized_digest(
        self,
    ):
        settings = (
            load_document_recovery_monitoring_settings(
                {
                    "DOCUMENT_RECOVERY_STATUS_ENABLED": "true",
                    "DOCUMENT_RECOVERY_STATUS_TOKEN_SHA256": (
                        TOKEN_SHA256.upper()
                    ),
                }
            )
        )

        self.assertTrue(
            settings.enabled
        )

        self.assertEqual(
            settings.token_sha256,
            TOKEN_SHA256,
        )

    def test_enabled_monitoring_requires_digest(
        self,
    ):
        with self.assertRaises(
            DocumentRecoveryMonitoringConfigurationError
        ):
            load_document_recovery_monitoring_settings(
                {
                    "DOCUMENT_RECOVERY_STATUS_ENABLED": "true",
                }
            )

    def test_malformed_digest_is_rejected(
        self,
    ):
        with self.assertRaises(
            DocumentRecoveryMonitoringConfigurationError
        ):
            load_document_recovery_monitoring_settings(
                {
                    "DOCUMENT_RECOVERY_STATUS_TOKEN_SHA256": "not-a-digest",
                }
            )


class DocumentRecoveryMonitoringApiTests(
    unittest.TestCase
):
    def test_missing_authorization_returns_401(
        self,
    ):
        with TestClient(
            monitoring_app()
        ) as client:
            response = client.get(
                "/admin/document-recovery/status"
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

    def test_invalid_bearer_token_returns_401(
        self,
    ):
        with TestClient(
            monitoring_app()
        ) as client:
            response = client.get(
                "/admin/document-recovery/status",
                headers=authorization_headers(
                    "wrong-token"
                ),
            )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_authorized_initializing_response_is_safe(
        self,
    ):
        with TestClient(
            monitoring_app()
        ) as client:
            response = client.get(
                "/admin/document-recovery/status",
                headers=authorization_headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["status"],
            "initializing",
        )

        self.assertFalse(
            payload["ready"]
        )

        self.assertNotIn(
            "error",
            payload,
        )

    def test_authorized_report_is_sanitized(
        self,
    ):
        report = DocumentRecoveryStartupReport(
            status="completed_with_failures",
            enabled=True,
            total_examined=12,
            candidate_count=4,
            processing_recovered_count=2,
            deleting_completed_count=1,
            failure_count=1,
            skipped_count=0,
            recent_count=5,
            invalid_timestamp_count=2,
            deferred_count=1,
            error=(
                "Database password and "
                "private storage key"
            ),
        )

        with TestClient(
            monitoring_app(report)
        ) as client:
            response = client.get(
                "/admin/document-recovery/status",
                headers=authorization_headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["status"],
            "completed_with_failures",
        )

        self.assertTrue(
            payload["attention_required"]
        )

        self.assertEqual(
            payload["counts"]["failures"],
            1,
        )

        serialized = json.dumps(
            payload
        ).casefold()

        self.assertNotIn(
            "password",
            serialized,
        )

        self.assertNotIn(
            "storage key",
            serialized,
        )

        self.assertNotIn(
            "error",
            payload,
        )

    def test_disabled_create_app_omits_endpoint(
        self,
    ):
        from app import main as main_module

        with (
            patch.object(
                main_module,
                "load_branch_merge_settings",
                return_value=SimpleNamespace(
                    enabled=False
                ),
            ),
            patch.object(
                main_module,
                "validate_branch_merge_settings",
            ),
            patch.object(
                main_module,
                "get_document_storage",
                return_value=object(),
            ),
            patch.object(
                main_module,
                "initialize_rag_runtime",
                return_value=object(),
            ),
        ):
            application = main_module.create_app(
                document_recovery_monitoring_settings=(
                    DocumentRecoveryMonitoringSettings(
                        enabled=False,
                        token_sha256="",
                    )
                )
            )

        self.assertNotIn(
            "/admin/document-recovery/status",
            application.openapi()["paths"],
        )

    def test_enabled_create_app_registers_endpoint(
        self,
    ):
        from app import main as main_module

        recovery_report = (
            DocumentRecoveryStartupReport(
                status="disabled",
                enabled=False,
                total_examined=0,
                candidate_count=0,
                processing_recovered_count=0,
                deleting_completed_count=0,
                failure_count=0,
                skipped_count=0,
                recent_count=0,
                invalid_timestamp_count=0,
                deferred_count=0,
            )
        )

        with (
            patch.object(
                main_module,
                "load_branch_merge_settings",
                return_value=SimpleNamespace(
                    enabled=False
                ),
            ),
            patch.object(
                main_module,
                "validate_branch_merge_settings",
            ),
            patch.object(
                main_module,
                "get_document_storage",
                return_value=object(),
            ),
            patch.object(
                main_module,
                "initialize_rag_runtime",
                return_value=object(),
            ),
        ):
            application = main_module.create_app(
                document_recovery_settings=(
                    DocumentRecoverySettings(
                        enabled=False,
                        stale_after_seconds=900,
                        batch_size=25,
                    )
                ),
                document_recovery_runner=Mock(
                    return_value=recovery_report
                ),
                document_recovery_rag=object(),
                document_recovery_monitoring_settings=(
                    enabled_monitoring_settings()
                ),
            )

            specification = (
                application.openapi()
            )

            self.assertIn(
                "/admin/document-recovery/status",
                specification["paths"],
            )

            with TestClient(
                application
            ) as client:
                response = client.get(
                    "/admin/document-recovery/status",
                    headers=authorization_headers(),
                )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()["status"],
            "disabled",
        )


if __name__ == "__main__":
    unittest.main()
