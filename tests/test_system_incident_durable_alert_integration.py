from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

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
from app.main import create_app


def monitoring_settings():
    signature = inspect.signature(
        SystemHealthMonitoringSettings
    )

    arguments = {}

    for name in signature.parameters:
        if name == "enabled":
            arguments[name] = True
        elif name == "token_sha256":
            arguments[name] = "a" * 64

    return SystemHealthMonitoringSettings(
        **arguments
    )


def alert_settings():
    return SystemIncidentAlertingSettings(
        enabled=True,
        webhook_url=(
            "https://alerts.example.test/hook"
        ),
        timeout_seconds=2,
    )


def request():
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": SYSTEM_HEALTH_STATUS_PATH,
            "raw_path": (
                SYSTEM_HEALTH_STATUS_PATH.encode(
                    "ascii"
                )
            ),
            "query_string": b"",
            "headers": [],
            "client": (
                "127.0.0.1",
                50000,
            ),
            "server": (
                "testserver",
                443,
            ),
        }
    )


def opened_evaluation():
    return {
        "service": "system_incidents",
        "observed_at": (
            "2026-07-22T12:00:00+00:00"
        ),
        "opened": [
            {
                "incident_key": (
                    "system_health:database"
                ),
                "component": "database",
                "severity": "critical",
                "source_status": "unavailable",
                "detail": "database_unreachable",
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
    value["opened"] = []
    value["unchanged"] = [
        {
            "incident_key": (
                "system_health:database"
            ),
        }
    ]
    return value


def endpoint_for(router):
    return next(
        route.endpoint
        for route in router.routes
        if route.path
        == SYSTEM_HEALTH_STATUS_PATH
    )


class SystemIncidentDurableAlertIntegrationTests(
    unittest.TestCase
):
    def invoke(
        self,
        *,
        recorder,
        enqueuer,
        worker,
        authenticated=True,
    ):
        router = create_system_health_admin_router(
            monitoring_settings(),
            definitions_provider=lambda _request: (),
            incident_recorder=recorder,
            incident_db_path="test-alerts.db",
            incident_alert_settings=(
                alert_settings()
            ),
            incident_alert_enqueuer=enqueuer,
            incident_alert_worker=worker,
        )

        background_tasks = BackgroundTasks()
        report = SimpleNamespace(
            checked_at=(
                "2026-07-22T12:00:00+00:00"
            )
        )

        with (
            patch(
                (
                    "app.api.system_health_admin."
                    "verify_branch_merge_bearer"
                ),
                return_value=authenticated,
            ),
            patch(
                (
                    "app.api.system_health_admin."
                    "_run_health_report"
                ),
                return_value=report,
            ),
            patch(
                (
                    "app.api.system_health_admin."
                    "system_health_payload"
                ),
                return_value={
                    "service": "system_health",
                    "status": "healthy",
                },
            ),
        ):
            response = endpoint_for(
                router
            )(
                request(),
                background_tasks,
            )

        return (
            response,
            background_tasks,
        )

    def test_persistence_precedes_enqueue_and_worker(
        self,
    ):
        events = []

        def recorder(
            _report,
            *,
            observed_at,
            db_path,
        ):
            events.append(
                (
                    "persist",
                    observed_at,
                    db_path,
                )
            )
            return opened_evaluation()

        def enqueuer(
            _settings,
            _evaluation,
            *,
            db_path,
        ):
            events.append(
                (
                    "enqueue",
                    db_path,
                )
            )
            return {
                "queued": True,
                "delivery_id": "delivery-1",
            }

        def worker(
            _settings,
            *,
            db_path,
        ):
            events.append(
                (
                    "worker",
                    db_path,
                )
            )

        response, background_tasks = (
            self.invoke(
                recorder=recorder,
                enqueuer=enqueuer,
                worker=worker,
            )
        )

        self.assertEqual(
            response["status"],
            "healthy",
        )
        self.assertEqual(
            [
                event[0]
                for event in events
            ],
            [
                "persist",
                "enqueue",
            ],
        )
        self.assertEqual(
            len(
                background_tasks.tasks
            ),
            1,
        )

        task = background_tasks.tasks[0]
        task.func(
            *task.args,
            **task.kwargs,
        )

        self.assertEqual(
            [
                event[0]
                for event in events
            ],
            [
                "persist",
                "enqueue",
                "worker",
            ],
        )

    def test_unchanged_only_evaluation_is_not_queued(
        self,
    ):
        enqueuer = MagicMock()
        worker = MagicMock()

        response, background_tasks = (
            self.invoke(
                recorder=(
                    lambda *_args, **_kwargs: (
                        unchanged_evaluation()
                    )
                ),
                enqueuer=enqueuer,
                worker=worker,
            )
        )

        self.assertEqual(
            response["status"],
            "healthy",
        )
        enqueuer.assert_not_called()
        worker.assert_not_called()
        self.assertEqual(
            background_tasks.tasks,
            [],
        )

    def test_persistence_failure_creates_no_alert_work(
        self,
    ):
        enqueuer = MagicMock()
        worker = MagicMock()

        def failing_recorder(
            *_args,
            **_kwargs,
        ):
            raise RuntimeError(
                "private database detail"
            )

        response, background_tasks = (
            self.invoke(
                recorder=failing_recorder,
                enqueuer=enqueuer,
                worker=worker,
            )
        )

        self.assertEqual(
            response["status"],
            "healthy",
        )
        enqueuer.assert_not_called()
        worker.assert_not_called()
        self.assertEqual(
            background_tasks.tasks,
            [],
        )

    def test_enqueue_failure_never_replaces_health_response(
        self,
    ):
        worker = MagicMock()

        def failing_enqueuer(
            *_args,
            **_kwargs,
        ):
            raise RuntimeError(
                "private outbox detail"
            )

        response, background_tasks = (
            self.invoke(
                recorder=(
                    lambda *_args, **_kwargs: (
                        opened_evaluation()
                    )
                ),
                enqueuer=failing_enqueuer,
                worker=worker,
            )
        )

        self.assertEqual(
            response["status"],
            "healthy",
        )
        worker.assert_not_called()
        self.assertEqual(
            background_tasks.tasks,
            [],
        )

    def test_worker_failure_isolated_from_health_response(
        self,
    ):
        def failing_worker(
            *_args,
            **_kwargs,
        ):
            raise RuntimeError(
                "private provider detail"
            )

        response, background_tasks = (
            self.invoke(
                recorder=(
                    lambda *_args, **_kwargs: (
                        opened_evaluation()
                    )
                ),
                enqueuer=(
                    lambda *_args, **_kwargs: {
                        "queued": True,
                    }
                ),
                worker=failing_worker,
            )
        )

        self.assertEqual(
            response["status"],
            "healthy",
        )
        self.assertEqual(
            len(
                background_tasks.tasks
            ),
            1,
        )

        task = background_tasks.tasks[0]
        task.func(
            *task.args,
            **task.kwargs,
        )

    def test_unauthorized_request_performs_no_work(
        self,
    ):
        recorder = MagicMock()
        enqueuer = MagicMock()
        worker = MagicMock()

        with self.assertRaises(
            HTTPException
        ) as captured:
            self.invoke(
                recorder=recorder,
                enqueuer=enqueuer,
                worker=worker,
                authenticated=False,
            )

        self.assertEqual(
            captured.exception.status_code,
            401,
        )
        recorder.assert_not_called()
        enqueuer.assert_not_called()
        worker.assert_not_called()

    def test_create_app_exposes_durable_injection_points(
        self,
    ):
        parameters = inspect.signature(
            create_app
        ).parameters

        self.assertIn(
            "system_incident_alert_enqueuer",
            parameters,
        )
        self.assertIn(
            "system_incident_alert_worker",
            parameters,
        )


if __name__ == "__main__":
    unittest.main()
