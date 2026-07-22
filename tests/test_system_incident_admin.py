from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system_incident_admin import (
    SYSTEM_INCIDENT_HISTORY_PATH,
    SYSTEM_INCIDENT_SUMMARY_PATH,
    create_system_incident_admin_router,
)
from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
)


TOKEN = "incident-admin-test-token"
TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode(
        "utf-8"
    )
).hexdigest()

AUTHORIZATION_HEADERS = {
    "Authorization": (
        "Bearer "
        + TOKEN
    ),
}


def valid_incident() -> dict:
    return {
        "incident_id": "incident-1",
        "incident_key": (
            "system_health:database"
        ),
        "component": "database",
        "severity": "critical",
        "source_status": "unavailable",
        "detail": "database_unreachable",
        "critical": True,
        "state": "open",
        "fingerprint": "a" * 64,
        "opened_at": (
            "2026-07-21T10:00:00+00:00"
        ),
        "last_seen_at": (
            "2026-07-21T10:01:00+00:00"
        ),
        "resolved_at": None,
        "occurrence_count": 2,
    }


def enabled_settings():
    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=TOKEN_DIGEST,
    )


def build_client(
    *,
    history_lister=lambda limit, state=None: [],
    summary_summarizer=lambda limit: {},
):
    application = FastAPI()

    application.include_router(
        create_system_incident_admin_router(
            enabled_settings(),
            history_lister=history_lister,
            summary_summarizer=(
                summary_summarizer
            ),
        )
    )

    return TestClient(
        application
    )


class SystemIncidentAdminTests(
    unittest.TestCase
):
    def test_history_requires_bearer_token(
        self,
    ):
        called = False

        def lister(
            limit,
            state=None,
        ):
            nonlocal called
            called = True
            return []

        client = build_client(
            history_lister=lister
        )

        response = client.get(
            SYSTEM_INCIDENT_HISTORY_PATH
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
        self.assertFalse(
            called
        )

    def test_summary_requires_bearer_token(
        self,
    ):
        called = False

        def summarizer(
            limit,
        ):
            nonlocal called
            called = True
            return {}

        client = build_client(
            summary_summarizer=summarizer
        )

        response = client.get(
            SYSTEM_INCIDENT_SUMMARY_PATH
        )

        self.assertEqual(
            response.status_code,
            401,
        )
        self.assertFalse(
            called
        )

    def test_wrong_bearer_is_rejected(
        self,
    ):
        client = build_client()

        response = client.get(
            SYSTEM_INCIDENT_HISTORY_PATH,
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

    def test_history_is_bounded_and_sanitized(
        self,
    ):
        calls = []

        def lister(
            limit,
            state=None,
        ):
            calls.append(
                (
                    limit,
                    state,
                )
            )

            return [
                valid_incident(),
            ]

        client = build_client(
            history_lister=lister
        )

        response = client.get(
            (
                SYSTEM_INCIDENT_HISTORY_PATH
                + "?limit=7"
            ),
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            calls,
            [
                (
                    7,
                    None,
                ),
            ],
        )
        self.assertEqual(
            payload["service"],
            "system_incidents",
        )
        self.assertEqual(
            payload["limit"],
            7,
        )
        self.assertEqual(
            payload["count"],
            1,
        )
        self.assertEqual(
            payload["history"][0],
            valid_incident(),
        )

    def test_history_state_filter_is_forwarded(
        self,
    ):
        calls = []

        def lister(
            limit,
            state=None,
        ):
            calls.append(
                (
                    limit,
                    state,
                )
            )
            return []

        client = build_client(
            history_lister=lister
        )

        response = client.get(
            (
                SYSTEM_INCIDENT_HISTORY_PATH
                + "?state=resolved"
            ),
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            calls,
            [
                (
                    20,
                    "resolved",
                ),
            ],
        )
        self.assertEqual(
            response.json()["state"],
            "resolved",
        )

    def test_summary_is_sanitized(
        self,
    ):
        client = build_client(
            summary_summarizer=(
                lambda limit: {
                    "total_incidents": 3,
                    "active_count": 2,
                    "resolved_count": 1,
                    "active_warning_count": 1,
                    "active_critical_count": 1,
                    "has_active_critical": True,
                    "total_occurrences": 8,
                    "latest_incident": (
                        valid_incident()
                    ),
                }
            )
        )

        response = client.get(
            (
                SYSTEM_INCIDENT_SUMMARY_PATH
                + "?limit=9"
            ),
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["window_limit"],
            9,
        )
        self.assertEqual(
            payload["summary"][
                "active_critical_count"
            ],
            1,
        )
        self.assertEqual(
            payload["summary"][
                "latest_incident"
            ],
            valid_incident(),
        )

    def test_limits_are_validated_before_service_call(
        self,
    ):
        called = False

        def lister(
            limit,
            state=None,
        ):
            nonlocal called
            called = True
            return []

        client = build_client(
            history_lister=lister
        )

        for invalid_limit in (
            0,
            101,
        ):
            with self.subTest(
                invalid_limit=invalid_limit
            ):
                response = client.get(
                    (
                        SYSTEM_INCIDENT_HISTORY_PATH
                        + "?limit="
                        + str(
                            invalid_limit
                        )
                    ),
                    headers=(
                        AUTHORIZATION_HEADERS
                    ),
                )

                self.assertEqual(
                    response.status_code,
                    422,
                )

        self.assertFalse(
            called
        )

    def test_state_is_validated_before_service_call(
        self,
    ):
        called = False

        def lister(
            limit,
            state=None,
        ):
            nonlocal called
            called = True
            return []

        client = build_client(
            history_lister=lister
        )

        response = client.get(
            (
                SYSTEM_INCIDENT_HISTORY_PATH
                + "?state=unknown"
            ),
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            422,
        )
        self.assertFalse(
            called
        )

    def test_history_failure_is_generic(
        self,
    ):
        def failing_lister(
            limit,
            state=None,
        ):
            raise RuntimeError(
                "postgresql://user:"
                "password@host/database"
            )

        client = build_client(
            history_lister=(
                failing_lister
            )
        )

        response = client.get(
            SYSTEM_INCIDENT_HISTORY_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "System incident history "
                    "is unavailable."
                ),
            },
        )
        self.assertNotIn(
            "password",
            response.text.casefold(),
        )

    def test_summary_failure_is_generic(
        self,
    ):
        def failing_summarizer(
            limit,
        ):
            raise RuntimeError(
                "secret storage key"
            )

        client = build_client(
            summary_summarizer=(
                failing_summarizer
            )
        )

        response = client.get(
            SYSTEM_INCIDENT_SUMMARY_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertNotIn(
            "secret",
            response.text.casefold(),
        )

    def test_unexpected_values_are_clamped(
        self,
    ):
        unsafe_row = {
            "incident_id": (
                "postgresql://password"
            ),
            "incident_key": "<script>",
            "component": "DATABASE PASSWORD",
            "severity": "root",
            "source_status": "exploded",
            "detail": (
                "password=do-not-return"
            ),
            "critical": "false",
            "state": "corrupt",
            "fingerprint": "credential",
            "opened_at": "secret",
            "last_seen_at": "secret",
            "resolved_at": "secret",
            "occurrence_count": -99,
            "database_url": (
                "postgresql://secret"
            ),
        }

        client = build_client(
            history_lister=(
                lambda limit, state=None: [
                    unsafe_row,
                    "not-a-row",
                ]
            )
        )

        response = client.get(
            SYSTEM_INCIDENT_HISTORY_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["count"],
            1,
        )

        row = payload["history"][0]

        self.assertEqual(
            row["incident_id"],
            "invalid",
        )
        self.assertEqual(
            row["incident_key"],
            "system_health:unknown",
        )
        self.assertEqual(
            row["component"],
            "unknown",
        )
        self.assertEqual(
            row["severity"],
            "warning",
        )
        self.assertEqual(
            row["source_status"],
            "unavailable",
        )
        self.assertEqual(
            row["detail"],
            "check_failed",
        )
        self.assertFalse(
            row["critical"]
        )
        self.assertEqual(
            row["state"],
            "resolved",
        )
        self.assertEqual(
            row["fingerprint"],
            "0" * 64,
        )
        self.assertEqual(
            row["occurrence_count"],
            1,
        )

        serialized = response.text.casefold()

        for forbidden in (
            "password",
            "credential",
            "database_url",
            "script",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_routes_are_read_only(
        self,
    ):
        client = build_client()

        for path in (
            SYSTEM_INCIDENT_HISTORY_PATH,
            SYSTEM_INCIDENT_SUMMARY_PATH,
        ):
            with self.subTest(
                path=path
            ):
                response = client.post(
                    path,
                    headers=(
                        AUTHORIZATION_HEADERS
                    ),
                )

                self.assertEqual(
                    response.status_code,
                    405,
                )

    def test_invalid_dependencies_are_rejected(
        self,
    ):
        with self.assertRaises(
            TypeError
        ):
            create_system_incident_admin_router(
                enabled_settings(),
                history_lister=None,
            )

        with self.assertRaises(
            TypeError
        ):
            create_system_incident_admin_router(
                enabled_settings(),
                summary_summarizer=None,
            )

    def test_invalid_service_shapes_are_generic(
        self,
    ):
        history_client = build_client(
            history_lister=(
                lambda limit, state=None: {}
            )
        )

        summary_client = build_client(
            summary_summarizer=(
                lambda limit: []
            )
        )

        history_response = history_client.get(
            SYSTEM_INCIDENT_HISTORY_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        summary_response = summary_client.get(
            SYSTEM_INCIDENT_SUMMARY_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            history_response.status_code,
            503,
        )
        self.assertEqual(
            summary_response.status_code,
            503,
        )

    def test_main_source_wires_routes_inside_health_gate(
        self,
    ):
        main_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "main.py"
        )

        source = main_path.read_text(
            encoding="utf-8-sig"
        )

        gate_index = source.index(
            "if system_health_settings.enabled:"
        )

        incident_import_index = source.index(
            (
                "from app.api.system_incident_admin "
                "import"
            )
        )

        incident_router_index = source.index(
            "create_system_incident_admin_router("
        )

        merge_gate_index = source.index(
            "if merge_settings.enabled:"
        )

        self.assertLess(
            gate_index,
            incident_import_index,
        )
        self.assertLess(
            incident_import_index,
            incident_router_index,
        )
        self.assertLess(
            incident_router_index,
            merge_gate_index,
        )
        self.assertIn(
            "application.include_router(",
            source[
                incident_router_index:
                merge_gate_index
            ],
        )


if __name__ == "__main__":
    unittest.main()
