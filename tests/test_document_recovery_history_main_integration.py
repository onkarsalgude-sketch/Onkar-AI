from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config.document_recovery_monitoring import (
    DocumentRecoveryMonitoringSettings,
)
from app.main import create_app


TOKEN = "v2.30.2-main-router-token"

TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode(
        "utf-8"
    )
).hexdigest().upper()


class DocumentRecoveryHistoryMainIntegrationTests(
    unittest.TestCase
):
    def build_application(
        self,
    ):
        settings = (
            DocumentRecoveryMonitoringSettings(
                enabled=True,
                token_sha256=TOKEN_DIGEST,
            )
        )

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
                document_recovery_monitoring_settings=(
                    settings
                ),
                document_recovery_runner=(
                    lambda **ignored: None
                ),
                document_recovery_rag=object(),
            )

    def test_main_registers_all_recovery_routes(
        self,
    ):
        application = self.build_application()

        paths = application.openapi()[
            "paths"
        ]

        required_paths = {
            "/admin/document-recovery/status",
            "/admin/document-recovery/history",
            "/admin/document-recovery/metrics",
        }

        self.assertTrue(
            required_paths.issubset(
                set(paths)
            )
        )

        for path in required_paths:
            methods = set(
                paths[path]
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

    def test_all_recovery_routes_require_authentication(
        self,
    ):
        application = self.build_application()

        required_paths = (
            "/admin/document-recovery/status",
            "/admin/document-recovery/history",
            "/admin/document-recovery/metrics",
        )

        with TestClient(
            application
        ) as client:
            responses = {
                path: client.get(path)
                for path in required_paths
            }

        for path, response in responses.items():
            with self.subTest(
                path=path
            ):
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


if __name__ == "__main__":
    unittest.main()
