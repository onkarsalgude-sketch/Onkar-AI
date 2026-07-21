from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import (
    document_recovery_admin,
)
from app.api.document_recovery_history_admin import (
    create_document_recovery_history_admin_router,
)


ROOT = Path(__file__).resolve().parents[1]

TOKEN = "recovery-history-admin-token"

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
            token_sha256=TOKEN_DIGEST,
        )
    )


def authorization_headers():
    return {
        "Authorization": (
            f"Bearer {TOKEN}"
        ),
    }


def safe_history_row():
    return {
        "run_id": "run-history-1",
        "status": "completed",
        "recovery_enabled": True,
        "started_at": (
            "2026-07-21T10:00:00+00:00"
        ),
        "finished_at": (
            "2026-07-21T10:00:01+00:00"
        ),
        "duration_ms": 1000,
        "total_examined": 3,
        "candidate_count": 2,
        "processing_recovered_count": 1,
        "deleting_completed_count": 1,
        "failure_count": 0,
        "skipped_count": 0,
        "recent_count": 1,
        "invalid_timestamp_count": 0,
        "deferred_count": 0,
        "error": "SECRET exception",
        "filename": "private.pdf",
        "document_id": "private-document-id",
        "file_path": "C:/private/path",
        "database_url": "postgresql://secret",
    }


def build_client(
    *,
    history_lister=None,
    metrics_summarizer=None,
):
    router_arguments = {}

    if history_lister is not None:
        router_arguments[
            "history_lister"
        ] = history_lister

    if metrics_summarizer is not None:
        router_arguments[
            "metrics_summarizer"
        ] = metrics_summarizer

    application = FastAPI()

    application.include_router(
        create_document_recovery_history_admin_router(
            monitoring_settings(),
            **router_arguments,
        )
    )

    return TestClient(
        application
    )


class DocumentRecoveryHistoryAdminTests(
    unittest.TestCase
):
    def test_history_requires_bearer_token(
        self,
    ):
        lister = MagicMock(
            return_value=[]
        )

        with build_client(
            history_lister=lister
        ) as client:
            response = client.get(
                "/admin/document-recovery/history"
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

        lister.assert_not_called()

    def test_metrics_requires_bearer_token(
        self,
    ):
        summarizer = MagicMock(
            return_value={}
        )

        with build_client(
            metrics_summarizer=summarizer
        ) as client:
            response = client.get(
                "/admin/document-recovery/metrics"
            )

        self.assertEqual(
            response.status_code,
            401,
        )

        summarizer.assert_not_called()

    def test_history_is_bounded_and_sanitized(
        self,
    ):
        lister = MagicMock(
            return_value=[
                safe_history_row()
            ]
        )

        with build_client(
            history_lister=lister
        ) as client:
            response = client.get(
                (
                    "/admin/document-recovery/"
                    "history?limit=7"
                ),
                headers=authorization_headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        lister.assert_called_once_with(
            7
        )

        payload = response.json()

        self.assertEqual(
            payload["service"],
            "document_recovery",
        )

        self.assertEqual(
            payload["limit"],
            7,
        )

        self.assertEqual(
            payload["count"],
            1,
        )

        stored = payload["history"][0]

        self.assertEqual(
            stored["run_id"],
            "run-history-1",
        )

        for forbidden_key in (
            "error",
            "filename",
            "document_id",
            "file_path",
            "database_url",
        ):
            self.assertNotIn(
                forbidden_key,
                stored,
            )

        serialized = repr(payload)

        self.assertNotIn(
            "SECRET",
            serialized,
        )

        self.assertNotIn(
            "private.pdf",
            serialized,
        )

    def test_metrics_are_sanitized(
        self,
    ):
        raw_latest = safe_history_row()

        raw_metrics = {
            "total_runs": 2,
            "status_counts": {
                "completed": 1,
                "failed": 1,
                "secret_status": 999,
            },
            "failure_runs": 1,
            "total_failures": 1,
            "average_duration_ms": 1500.5,
            "latest_run": raw_latest,
            "error": "SECRET metrics error",
        }

        summarizer = MagicMock(
            return_value=raw_metrics
        )

        with build_client(
            metrics_summarizer=summarizer
        ) as client:
            response = client.get(
                (
                    "/admin/document-recovery/"
                    "metrics?limit=25"
                ),
                headers=authorization_headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        summarizer.assert_called_once_with(
            25
        )

        payload = response.json()

        self.assertEqual(
            payload["window_limit"],
            25,
        )

        metrics = payload["metrics"]

        self.assertEqual(
            metrics["total_runs"],
            2,
        )

        self.assertEqual(
            metrics["failure_runs"],
            1,
        )

        self.assertEqual(
            metrics["total_failures"],
            1,
        )

        self.assertEqual(
            metrics["average_duration_ms"],
            1500.5,
        )

        self.assertNotIn(
            "secret_status",
            metrics["status_counts"],
        )

        self.assertNotIn(
            "error",
            metrics["latest_run"],
        )

        self.assertNotIn(
            "SECRET",
            repr(payload),
        )

    def test_limits_are_validated_before_service_call(
        self,
    ):
        lister = MagicMock(
            return_value=[]
        )

        summarizer = MagicMock(
            return_value={}
        )

        with build_client(
            history_lister=lister,
            metrics_summarizer=summarizer,
        ) as client:
            history_zero = client.get(
                (
                    "/admin/document-recovery/"
                    "history?limit=0"
                ),
                headers=authorization_headers(),
            )

            history_large = client.get(
                (
                    "/admin/document-recovery/"
                    "history?limit=101"
                ),
                headers=authorization_headers(),
            )

            metrics_zero = client.get(
                (
                    "/admin/document-recovery/"
                    "metrics?limit=0"
                ),
                headers=authorization_headers(),
            )

            metrics_large = client.get(
                (
                    "/admin/document-recovery/"
                    "metrics?limit=101"
                ),
                headers=authorization_headers(),
            )

        for response in (
            history_zero,
            history_large,
            metrics_zero,
            metrics_large,
        ):
            self.assertEqual(
                response.status_code,
                422,
            )

        lister.assert_not_called()
        summarizer.assert_not_called()

    def test_service_failure_is_generic(
        self,
    ):
        def failing_lister(
            limit,
        ):
            raise RuntimeError(
                "SECRET database connection"
            )

        with build_client(
            history_lister=failing_lister
        ) as client:
            response = client.get(
                "/admin/document-recovery/history",
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
                    "Document recovery history "
                    "is unavailable."
                )
            },
        )

        self.assertNotIn(
            "SECRET",
            response.text,
        )

    def test_unexpected_values_are_clamped(
        self,
    ):
        row = safe_history_row()

        row["duration_ms"] = -10
        row["failure_count"] = "invalid"
        row["recovery_enabled"] = 1
        row["status"] = "private-status"

        with build_client(
            history_lister=(
                lambda limit: [row]
            )
        ) as client:
            response = client.get(
                "/admin/document-recovery/history",
                headers=authorization_headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        stored = response.json()[
            "history"
        ][0]

        self.assertEqual(
            stored["duration_ms"],
            0,
        )

        self.assertEqual(
            stored["failure_count"],
            0,
        )

        self.assertEqual(
            stored["status"],
            "unknown",
        )

    def test_main_includes_history_admin_router(
        self,
    ):
        main_path = (
            ROOT
            / "app"
            / "main.py"
        )

        source = main_path.read_text(
            encoding="utf-8-sig"
        )

        tree = ast.parse(
            source,
            filename=str(main_path),
        )

        imported = False
        included = False

        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.ImportFrom,
            ):
                if (
                    node.module
                    == (
                        "app.api."
                        "document_recovery_history_admin"
                    )
                    and any(
                        alias.name
                        == (
                            "create_document_recovery_"
                            "history_admin_router"
                        )
                        for alias in node.names
                    )
                ):
                    imported = True

            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            if not (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                == "include_router"
            ):
                continue

            if (
                node.args
                and isinstance(
                    node.args[0],
                    ast.Name,
                )
                and node.args[0].id
                == (
                    "recovery_history_admin_router"
                )
            ):
                included = True

        self.assertTrue(
            imported
        )

        self.assertTrue(
            included
        )


if __name__ == "__main__":
    unittest.main()
