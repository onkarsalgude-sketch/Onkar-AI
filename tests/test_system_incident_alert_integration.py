from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system_health_admin import (
    SYSTEM_HEALTH_STATUS_PATH,
    create_system_health_admin_router,
)
from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
)
from app.config.system_incident_alerting import (
    SystemIncidentAlertingSettings,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    degraded_outcome,
    unavailable_outcome,
)


TOKEN = "outbound-alert-integration-token"
TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode("utf-8")
).hexdigest()

AUTHORIZATION_HEADERS = {
    "Authorization": "Bearer " + TOKEN,
}

WEBHOOK_URL = (
    "https://alerts.example.test/"
    "hooks/private-token"
)


def health_settings():
    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=TOKEN_DIGEST,
    )


def alert_settings(enabled: bool):
    return SystemIncidentAlertingSettings(
        enabled=enabled,
        webhook_url=(
            WEBHOOK_URL
            if enabled
            else ""
        ),
        timeout_seconds=5.0,
    )


def definition(outcome):
    return HealthCheckDefinition(
        name="database",
        check=lambda: outcome,
        critical=True,
    )


def opened_evaluation():
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T10:00:00+00:00"
        ),
        "opened": [
            {
                "incident_key": (
                    "system_health:database"
                ),
                "component": "database",
                "severity": "critical",
                "source_status": "unavailable",
                "detail": (
                    "database_unreachable"
                ),
                "critical": True,
                "fingerprint": "a" * 64,
            }
        ],
        "updated": [],
        "resolved": [],
        "unchanged": [],
    }


def unchanged_evaluation():
    value = opened_evaluation()
    value["unchanged"] = value.pop(
        "opened"
    )
    value["opened"] = []
    return value


def build_client(
    *,
    incident_recorder,
    alerts_enabled,
    incident_alert_deliverer,
):
    application = FastAPI()

    application.include_router(
        create_system_health_admin_router(
            health_settings(),
            definitions_provider=(
                lambda request: (
                    definition(
                        unavailable_outcome(
                            "database_unreachable"
                        )
                    ),
                )
            ),
            incident_recorder=(
                incident_recorder
            ),
            incident_db_path=(
                "incident-alert-integration.db"
            ),
            incident_alert_settings=(
                alert_settings(
                    alerts_enabled
                )
            ),
            incident_alert_deliverer=(
                incident_alert_deliverer
            ),
        )
    )

    return TestClient(
        application
    )


class SystemIncidentAlertIntegrationTests(
    unittest.TestCase
):
    def test_disabled_alerts_schedule_no_delivery(
        self,
    ):
        deliveries = []

        client = build_client(
            incident_recorder=(
                lambda report, **kwargs: (
                    opened_evaluation()
                )
            ),
            alerts_enabled=False,
            incident_alert_deliverer=(
                lambda settings, evaluation: (
                    deliveries.append(
                        (
                            settings,
                            evaluation,
                        )
                    )
                )
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            deliveries,
            [],
        )

    def test_opened_transition_is_delivered_after_persistence(
        self,
    ):
        events = []

        def recorder(
            report,
            *,
            observed_at,
            db_path,
        ):
            del report
            del observed_at
            del db_path

            events.append(
                "persisted"
            )
            return opened_evaluation()

        def deliverer(
            settings,
            evaluation,
        ):
            events.append(
                "delivered"
            )
            self.assertTrue(
                settings.enabled
            )
            self.assertEqual(
                evaluation["opened"][0][
                    "component"
                ],
                "database",
            )

        client = build_client(
            incident_recorder=recorder,
            alerts_enabled=True,
            incident_alert_deliverer=(
                deliverer
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            events,
            [
                "persisted",
                "delivered",
            ],
        )

    def test_unchanged_only_evaluation_schedules_no_delivery(
        self,
    ):
        deliveries = []

        client = build_client(
            incident_recorder=(
                lambda report, **kwargs: (
                    unchanged_evaluation()
                )
            ),
            alerts_enabled=True,
            incident_alert_deliverer=(
                lambda settings, evaluation: (
                    deliveries.append(
                        (
                            settings,
                            evaluation,
                        )
                    )
                )
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            deliveries,
            [],
        )

    def test_persistence_failure_schedules_no_delivery(
        self,
    ):
        deliveries = []

        def failing_recorder(
            report,
            *,
            observed_at,
            db_path,
        ):
            del report
            del observed_at
            del db_path

            raise RuntimeError(
                "postgresql://user:"
                "password@host/database"
            )

        client = build_client(
            incident_recorder=(
                failing_recorder
            ),
            alerts_enabled=True,
            incident_alert_deliverer=(
                lambda settings, evaluation: (
                    deliveries.append(
                        (
                            settings,
                            evaluation,
                        )
                    )
                )
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            deliveries,
            [],
        )
        self.assertNotIn(
            "password",
            response.text.casefold(),
        )

    def test_delivery_failure_never_replaces_health_response(
        self,
    ):
        def failing_deliverer(
            settings,
            evaluation,
        ):
            del settings
            del evaluation

            raise RuntimeError(
                "private-token password secret"
            )

        client = build_client(
            incident_recorder=(
                lambda report, **kwargs: (
                    opened_evaluation()
                )
            ),
            alerts_enabled=True,
            incident_alert_deliverer=(
                failing_deliverer
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTHORIZATION_HEADERS,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        serialized = response.text.casefold()

        for forbidden in (
            "private-token",
            "password",
            "secret",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_unauthorized_request_performs_no_work(
        self,
    ):
        calls = {
            "recorder": 0,
            "deliverer": 0,
        }

        def recorder(
            report,
            **kwargs,
        ):
            del report
            del kwargs
            calls["recorder"] += 1
            return opened_evaluation()

        def deliverer(
            settings,
            evaluation,
        ):
            del settings
            del evaluation
            calls["deliverer"] += 1

        client = build_client(
            incident_recorder=recorder,
            alerts_enabled=True,
            incident_alert_deliverer=(
                deliverer
            ),
        )

        response = client.get(
            SYSTEM_HEALTH_STATUS_PATH
        )

        self.assertEqual(
            response.status_code,
            401,
        )
        self.assertEqual(
            calls,
            {
                "recorder": 0,
                "deliverer": 0,
            },
        )

    def test_invalid_alert_deliverer_is_rejected(
        self,
    ):
        with self.assertRaises(
            TypeError
        ):
            create_system_health_admin_router(
                health_settings(),
                definitions_provider=(
                    lambda request: ()
                ),
                incident_alert_settings=(
                    alert_settings(
                        True
                    )
                ),
                incident_alert_deliverer=(
                    "not-callable"
                ),
            )

    def test_main_wires_alerts_inside_health_gate(
        self,
    ):
        with open(
            "app/main.py",
            encoding="utf-8",
        ) as source_file:
            source = source_file.read()

        gate_index = source.index(
            "    if system_health_settings.enabled:"
        )

        enqueue_import_index = source.index(
            (
                "from app.services."
                "system_incident_alert_outbox_service "
                "import ("
            )
        )

        worker_import_index = source.index(
            (
                "from app.services."
                "system_incident_alert_outbox_worker "
                "import ("
            )
        )

        recorder_index = source.index(
            "record_system_incident_evaluation"
        )

        router_index = source.index(
            "create_system_health_admin_router("
        )

        self.assertLess(
            gate_index,
            enqueue_import_index,
        )

        self.assertLess(
            gate_index,
            worker_import_index,
        )

        self.assertLess(
            recorder_index,
            router_index,
        )

        self.assertIn(
            "system_incident_alert_enqueuer=None",
            source,
        )

        self.assertIn(
            "system_incident_alert_worker=None",
            source,
        )

        self.assertIn(
            "incident_alert_enqueuer=(",
            source,
        )

        self.assertIn(
            "incident_alert_worker=(",
            source,
        )

        self.assertNotIn(
            (
                "else "
                "deliver_system_incident_alerts"
            ),
            source,
        )


if __name__ == "__main__":
    unittest.main()
