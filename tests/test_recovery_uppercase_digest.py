from __future__ import annotations

import hashlib
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import document_recovery_admin
from app.api.document_recovery_admin import (
    create_document_recovery_admin_router,
)
from app.api.document_recovery_history_admin import (
    create_document_recovery_history_admin_router,
)
from app.services.branch_merge_security import (
    verify_branch_merge_bearer,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
)


TOKEN = "uppercase-recovery-digest-token"

TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode(
        "utf-8"
    )
).hexdigest()


def monitoring_settings():
    return (
        document_recovery_admin
        .DocumentRecoveryMonitoringSettings(
            enabled=True,
            token_sha256=(
                TOKEN_DIGEST.upper()
            ),
        )
    )


def build_client():
    application = FastAPI()

    application.state.document_recovery_report = (
        DocumentRecoveryStartupReport(
            status="completed",
            enabled=True,
            total_examined=0,
            candidate_count=0,
            processing_recovered_count=0,
            deleting_completed_count=0,
            failure_count=0,
            skipped_count=0,
            recent_count=0,
            invalid_timestamp_count=0,
            deferred_count=0,
            error=None,
        )
    )

    application.include_router(
        create_document_recovery_admin_router(
            monitoring_settings()
        )
    )

    application.include_router(
        create_document_recovery_history_admin_router(
            monitoring_settings(),
            history_lister=(
                lambda limit: []
            ),
            metrics_summarizer=(
                lambda limit: {
                    "total_runs": 0,
                    "status_counts": {},
                    "failure_runs": 0,
                    "total_failures": 0,
                    "average_duration_ms": 0.0,
                    "latest_run": None,
                }
            ),
        )
    )

    return TestClient(
        application
    )


class RecoveryUppercaseDigestTests(
    unittest.TestCase
):
    def test_shared_verifier_accepts_uppercase_digest(
        self,
    ):
        authenticated = (
            verify_branch_merge_bearer(
                f"Bearer {TOKEN}",
                TOKEN_DIGEST.upper(),
            )
        )

        self.assertTrue(
            authenticated
        )

    def test_uppercase_digest_authenticates_recovery_routes(
        self,
    ):
        headers = {
            "Authorization": (
                f"Bearer {TOKEN}"
            )
        }

        with build_client() as client:
            responses = (
                client.get(
                    "/admin/document-recovery/status",
                    headers=headers,
                ),
                client.get(
                    "/admin/document-recovery/history",
                    headers=headers,
                ),
                client.get(
                    "/admin/document-recovery/metrics",
                    headers=headers,
                ),
            )

        for response in responses:
            self.assertEqual(
                response.status_code,
                200,
            )

    def test_wrong_token_remains_rejected(
        self,
    ):
        wrong_header = (
            "Bearer definitely-wrong-token"
        )

        self.assertFalse(
            verify_branch_merge_bearer(
                wrong_header,
                TOKEN_DIGEST.upper(),
            )
        )

        headers = {
            "Authorization": wrong_header,
        }

        with build_client() as client:
            responses = (
                client.get(
                    "/admin/document-recovery/status",
                    headers=headers,
                ),
                client.get(
                    "/admin/document-recovery/history",
                    headers=headers,
                ),
                client.get(
                    "/admin/document-recovery/metrics",
                    headers=headers,
                ),
            )

        for response in responses:
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
