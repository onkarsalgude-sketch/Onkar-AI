from __future__ import annotations

import hashlib
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import app.main as main_module
from app.config.system_health_monitoring import (
    SystemHealthMonitoringSettings,
)
from app.config.system_incident_alerting import (
    DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS,
    MAX_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS,
    MIN_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS,
    SystemIncidentAlertingConfigurationError,
    SystemIncidentAlertingSettings,
    load_system_incident_alerting_settings,
    validate_system_incident_alerting_settings,
)


SAFE_WEBHOOK_URL = "https://alerts.example.test/hook"
SAFE_DATABASE_PATH = "startup-alert-recovery.db"


def enabled_system_health_settings(
) -> SystemHealthMonitoringSettings:
    token_digest = hashlib.sha256(
        b"startup-alert-recovery-token"
    ).hexdigest()

    return SystemHealthMonitoringSettings(
        enabled=True,
        token_sha256=token_digest,
    )


class SystemIncidentAlertStartupRecoveryTests(
    unittest.TestCase
):
    def build_application(
        self,
        *,
        alert_settings: SystemIncidentAlertingSettings,
        recovery: Mock,
        document_runner: Mock | None = None,
        worker: Mock | None = None,
        database_path: str = SAFE_DATABASE_PATH,
    ):
        resolved_document_runner = (
            document_runner
            if document_runner is not None
            else Mock(
                return_value={
                    "status": "document-completed",
                }
            )
        )
        resolved_worker = (
            worker
            if worker is not None
            else Mock()
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
                "load_document_recovery_monitoring_settings",
                return_value=SimpleNamespace(
                    enabled=False
                ),
            ),
            patch.object(
                main_module,
                "validate_document_recovery_monitoring_settings",
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
                document_recovery_runner=(
                    resolved_document_runner
                ),
                document_recovery_rag=object(),
                system_health_monitoring_settings=(
                    enabled_system_health_settings()
                ),
                system_health_definitions_provider=(
                    lambda request: ()
                ),
                system_incident_recorder=Mock(),
                system_incident_db_path=database_path,
                system_incident_alerting_settings=(
                    alert_settings
                ),
                system_incident_alert_enqueuer=Mock(),
                system_incident_alert_worker=(
                    resolved_worker
                ),
                system_incident_alert_recovery=recovery,
            )

        return (
            application,
            resolved_document_runner,
            resolved_worker,
        )

    def test_create_app_exposes_recovery_injection_point(
        self,
    ):
        parameters = inspect.signature(
            main_module.create_app
        ).parameters

        self.assertIn(
            "system_incident_alert_recovery",
            parameters,
        )

    def test_settings_default_to_safe_stale_interval(
        self,
    ):
        settings = load_system_incident_alerting_settings(
            {}
        )

        self.assertFalse(
            settings.enabled
        )
        self.assertEqual(
            settings.stale_after_seconds,
            DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS,
        )
        self.assertEqual(
            DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS,
            300.0,
        )

    def test_settings_load_and_validate_stale_interval(
        self,
    ):
        settings = load_system_incident_alerting_settings(
            {
                "SYSTEM_INCIDENT_ALERTS_ENABLED": "true",
                "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL": (
                    SAFE_WEBHOOK_URL
                ),
                "SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS": (
                    "120"
                ),
            }
        )

        self.assertEqual(
            settings.stale_after_seconds,
            120.0,
        )

    def test_settings_reject_invalid_stale_intervals(
        self,
    ):
        for value in (
            MIN_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
            - 0.1,
            MAX_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
            + 0.1,
        ):
            with self.subTest(value=value):
                settings = SystemIncidentAlertingSettings(
                    stale_after_seconds=value
                )

                with self.assertRaises(
                    SystemIncidentAlertingConfigurationError
                ):
                    validate_system_incident_alerting_settings(
                        settings
                    )

        for value in (
            True,
            "not-a-number",
        ):
            with self.subTest(value=value):
                with self.assertRaises(
                    SystemIncidentAlertingConfigurationError
                ):
                    SystemIncidentAlertingSettings(
                        stale_after_seconds=value
                    )

    def test_enabled_alerts_recover_once_before_requests(
        self,
    ):
        events = []

        def run_document_recovery(**kwargs):
            del kwargs
            events.append(
                "document"
            )
            return {
                "status": "document-completed",
            }

        def run_alert_recovery(**kwargs):
            del kwargs
            events.append(
                "alert"
            )
            return {
                "recovered_count": 2,
                "failed_count": 1,
            }

        document_runner = Mock(
            side_effect=run_document_recovery
        )
        recovery = Mock(
            side_effect=run_alert_recovery
        )
        worker = Mock()
        alert_settings = SystemIncidentAlertingSettings(
            enabled=True,
            webhook_url=SAFE_WEBHOOK_URL,
            timeout_seconds=2.0,
            stale_after_seconds=120.0,
        )

        (
            application,
            resolved_document_runner,
            resolved_worker,
        ) = self.build_application(
            alert_settings=alert_settings,
            recovery=recovery,
            document_runner=document_runner,
            worker=worker,
        )

        self.assertIsNone(
            application.state
            .system_incident_alert_recovery_report
        )

        with TestClient(
            application
        ) as client:
            self.assertEqual(
                events,
                [
                    "document",
                    "alert",
                ],
            )
            self.assertEqual(
                application.state
                .system_incident_alert_recovery_report,
                {
                    "status": "completed",
                    "recovered_count": 2,
                    "failed_count": 1,
                },
            )
            self.assertEqual(
                client.get(
                    "/"
                ).status_code,
                200,
            )

        resolved_document_runner.assert_called_once()
        recovery.assert_called_once_with(
            stale_after_seconds=120.0,
            db_path=SAFE_DATABASE_PATH,
        )
        resolved_worker.assert_not_called()

    def test_disabled_alerts_skip_startup_recovery(
        self,
    ):
        recovery = Mock()
        application, document_runner, worker = (
            self.build_application(
                alert_settings=(
                    SystemIncidentAlertingSettings(
                        enabled=False
                    )
                ),
                recovery=recovery,
            )
        )

        with TestClient(
            application
        ) as client:
            self.assertEqual(
                client.get(
                    "/"
                ).status_code,
                200,
            )
            self.assertEqual(
                application.state
                .system_incident_alert_recovery_report,
                {
                    "status": "disabled",
                    "recovered_count": 0,
                    "failed_count": 0,
                },
            )

        document_runner.assert_called_once()
        recovery.assert_not_called()
        worker.assert_not_called()

    def test_recovery_failure_is_nonfatal_and_generic(
        self,
    ):
        recovery = Mock(
            side_effect=RuntimeError(
                "private database detail"
            )
        )
        application, document_runner, worker = (
            self.build_application(
                alert_settings=(
                    SystemIncidentAlertingSettings(
                        enabled=True,
                        webhook_url=SAFE_WEBHOOK_URL,
                        stale_after_seconds=60.0,
                    )
                ),
                recovery=recovery,
            )
        )

        with patch.object(
            main_module.LOGGER,
            "error",
        ) as error_logger:
            with TestClient(
                application
            ) as client:
                self.assertEqual(
                    client.get(
                        "/"
                    ).status_code,
                    200,
                )

        report = (
            application.state
            .system_incident_alert_recovery_report
        )

        self.assertEqual(
            report,
            {
                "status": "failed",
                "recovered_count": 0,
                "failed_count": 0,
            },
        )
        self.assertNotIn(
            "private",
            repr(
                report
            ).casefold(),
        )
        error_logger.assert_called_once_with(
            "System incident alert startup recovery failed."
        )
        document_runner.assert_called_once()
        recovery.assert_called_once_with(
            stale_after_seconds=60.0,
            db_path=SAFE_DATABASE_PATH,
        )
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
