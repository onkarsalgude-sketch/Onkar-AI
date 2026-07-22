from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system_health_admin import (
    SYSTEM_HEALTH_STATUS_PATH,
    create_system_health_admin_router,
)
from app.config.database import DatabaseSettings
from app.config.system_health_monitoring import SystemHealthMonitoringSettings
from app.database.engine import build_database_engine
from app.database.migrations import initialize_schema
from app.services.system_health_service import (
    HealthCheckDefinition,
    degraded_outcome,
    healthy_outcome,
    unavailable_outcome,
)
from app.services.system_incident_history_service import (
    list_system_incidents,
    record_system_incident_evaluation,
)


TOKEN = "incident-integration-test-token"
TOKEN_DIGEST = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()
AUTH_HEADERS = {"Authorization": "Bearer " + TOKEN}


def settings():
    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=TOKEN_DIGEST,
    )


def definition(outcome):
    return HealthCheckDefinition(
        name="database",
        check=lambda: outcome,
        critical=True,
    )


def build_client(
    provider,
    *,
    recorder=None,
    db_path=None,
):
    application = FastAPI()
    application.include_router(
        create_system_health_admin_router(
            settings(),
            definitions_provider=provider,
            incident_recorder=recorder,
            incident_db_path=db_path,
        )
    )
    return TestClient(application)


def build_engine(path: Path):
    return build_database_engine(
        DatabaseSettings(
            backend="sqlite",
            database_url=None,
            sqlite_path=path,
            require_persistence=False,
            pool_size=5,
            connect_timeout_seconds=10,
        )
    )


class SystemIncidentEvaluationIntegrationTests(unittest.TestCase):
    def test_unauthorized_request_runs_no_check_or_write(self):
        calls = {"provider": 0, "recorder": 0}

        def provider(request):
            del request
            calls["provider"] += 1
            return (definition(healthy_outcome("postgresql_reachable")),)

        def recorder(report, *, observed_at, db_path):
            del report, observed_at, db_path
            calls["recorder"] += 1

        response = build_client(
            provider,
            recorder=recorder,
            db_path="unused.db",
        ).get(SYSTEM_HEALTH_STATUS_PATH)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(calls, {"provider": 0, "recorder": 0})

    def test_authenticated_evaluation_is_forwarded(self):
        recorded = []

        def provider(request):
            del request
            return (definition(degraded_outcome("database_slow")),)

        def recorder(report, *, observed_at, db_path):
            recorded.append((report, observed_at, db_path))

        response = build_client(
            provider,
            recorder=recorder,
            db_path="incident-test.db",
        ).get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTH_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(len(recorded), 1)
        report, observed_at, db_path = recorded[0]
        self.assertEqual(observed_at, report.checked_at)
        self.assertEqual(db_path, "incident-test.db")

    def test_fallback_report_is_forwarded_safely(self):
        recorded = []

        def provider(request):
            del request
            raise RuntimeError("R2 secret access key")

        def recorder(report, *, observed_at, db_path):
            recorded.append((report, observed_at, db_path))

        response = build_client(
            provider,
            recorder=recorder,
            db_path="fallback.db",
        ).get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTH_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unhealthy")
        self.assertEqual(recorded[0][0].components[0].name, "health_runtime")
        self.assertEqual(recorded[0][0].components[0].detail, "check_failed")
        self.assertNotIn("secret", response.text.casefold())

    def test_persistence_failure_never_replaces_health_response(self):
        def provider(request):
            del request
            return (
                definition(
                    unavailable_outcome("database_unreachable")
                ),
            )

        def failing_recorder(report, *, observed_at, db_path):
            del report, observed_at, db_path
            raise RuntimeError(
                "postgresql://user:password@host/database"
            )

        response = build_client(
            provider,
            recorder=failing_recorder,
            db_path="failure.db",
        ).get(
            SYSTEM_HEALTH_STATUS_PATH,
            headers=AUTH_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unhealthy")
        self.assertNotIn("password", response.text.casefold())
        self.assertNotIn("postgresql://", response.text.casefold())

    def test_invalid_recorder_is_rejected(self):
        with self.assertRaises(TypeError):
            create_system_health_admin_router(
                settings(),
                definitions_provider=lambda request: (),
                incident_recorder="not-callable",
            )

    def test_endpoint_drives_open_repeat_and_resolve_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "incidents.db"
            engine = build_engine(database_path)
            initialize_schema(engine)
            engine.dispose()

            state = {
                "outcome": unavailable_outcome("database_unreachable"),
            }

            def provider(request):
                del request
                return (definition(state["outcome"]),)

            ids = iter(("incident-integrated-1",))

            def recorder(report, *, observed_at, db_path):
                return record_system_incident_evaluation(
                    report,
                    observed_at=observed_at,
                    db_path=db_path,
                    connection_factory=lambda path: sqlite3.connect(path),
                    incident_id_factory=lambda: next(ids),
                )

            client = build_client(
                provider,
                recorder=recorder,
                db_path=str(database_path),
            )

            first = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
                headers=AUTH_HEADERS,
            )
            second = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
                headers=AUTH_HEADERS,
            )

            state["outcome"] = healthy_outcome("postgresql_reachable")

            third = client.get(
                SYSTEM_HEALTH_STATUS_PATH,
                headers=AUTH_HEADERS,
            )

            self.assertEqual(
                [first.status_code, second.status_code, third.status_code],
                [200, 200, 200],
            )

            rows = list_system_incidents(
                db_path=str(database_path),
                connection_factory=lambda path: sqlite3.connect(path),
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["incident_id"], "incident-integrated-1")
            self.assertEqual(rows[0]["state"], "resolved")
            self.assertEqual(rows[0]["occurrence_count"], 2)
            self.assertIsNotNone(rows[0]["resolved_at"])

    def test_main_wires_default_recorder_inside_health_gate(self):
        main_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "main.py"
        )
        source = main_path.read_text(encoding="utf-8-sig")

        gate_index = source.index("if system_health_settings.enabled:")
        recorder_import_index = source.index(
            "from app.services.system_incident_history_service import"
        )
        router_index = source.index("create_system_health_admin_router(")
        merge_gate_index = source.index("if merge_settings.enabled:")

        self.assertLess(gate_index, recorder_import_index)
        self.assertLess(recorder_import_index, router_index)
        self.assertLess(router_index, merge_gate_index)
        self.assertIn("system_incident_recorder=None", source)
        self.assertIn("system_incident_db_path=None", source)
        wired = source[router_index:merge_gate_index]
        self.assertIn("incident_recorder=(", wired)
        self.assertIn("incident_db_path=(", wired)


if __name__ == "__main__":
    unittest.main()
