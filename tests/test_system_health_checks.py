from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.system_health_checks import (
    SYSTEM_HEALTH_STORAGE_PROBE_KEY,
    build_default_health_check_definitions,
    check_database_health,
    check_document_recovery_health,
    check_document_storage_health,
)
from app.services.system_health_service import (
    SystemHealthConfigurationError,
    healthy_outcome,
)


class SystemHealthChecksTests(
    unittest.TestCase
):
    def database_settings(
        self,
        *,
        postgresql=False,
        sqlite=False,
    ):
        return SimpleNamespace(
            is_postgresql=postgresql,
            is_sqlite=sqlite,
        )

    def storage_settings(
        self,
        *,
        r2=False,
        local=False,
    ):
        return SimpleNamespace(
            is_r2=r2,
            is_local=local,
        )

    def healthy_database_engine(
        self,
        value=1,
    ):
        engine = MagicMock()

        connection = (
            engine.connect.return_value
            .__enter__.return_value
        )

        result = (
            connection.exec_driver_sql
            .return_value
        )

        result.scalar_one.return_value = (
            value
        )

        return engine

    def test_postgresql_database_probe_is_healthy(
        self,
    ):
        engine = self.healthy_database_engine()

        outcome = check_database_health(
            settings_loader=lambda: (
                self.database_settings(
                    postgresql=True
                )
            ),
            engine_builder=lambda settings: engine,
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "postgresql_reachable",
        )

        connection = (
            engine.connect.return_value
            .__enter__.return_value
        )

        connection.exec_driver_sql.assert_called_once_with(
            "SELECT 1"
        )

        engine.dispose.assert_called_once_with()

    def test_sqlite_database_probe_is_healthy(
        self,
    ):
        engine = self.healthy_database_engine()

        outcome = check_database_health(
            settings_loader=lambda: (
                self.database_settings(
                    sqlite=True
                )
            ),
            engine_builder=lambda settings: engine,
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "sqlite_reachable",
        )

    def test_database_invalid_response_is_unavailable(
        self,
    ):
        engine = self.healthy_database_engine(
            value=0
        )

        outcome = check_database_health(
            settings_loader=lambda: (
                self.database_settings(
                    postgresql=True
                )
            ),
            engine_builder=lambda settings: engine,
        )

        self.assertEqual(
            outcome.status,
            "unavailable",
        )
        self.assertEqual(
            outcome.detail,
            "database_response_invalid",
        )

    def test_database_configuration_failure_is_sanitized(
        self,
    ):
        def failing_loader():
            raise RuntimeError(
                "postgresql://user:secret@host/database"
            )

        outcome = check_database_health(
            settings_loader=failing_loader,
        )

        self.assertEqual(
            outcome.status,
            "unavailable",
        )
        self.assertEqual(
            outcome.detail,
            "database_unreachable",
        )

    def test_database_connection_failure_disposes_engine(
        self,
    ):
        engine = MagicMock()

        engine.connect.side_effect = (
            RuntimeError(
                "connection secret"
            )
        )

        outcome = check_database_health(
            settings_loader=lambda: (
                self.database_settings(
                    postgresql=True
                )
            ),
            engine_builder=lambda settings: engine,
        )

        self.assertEqual(
            outcome.status,
            "unavailable",
        )

        engine.dispose.assert_called_once_with()

    def test_invalid_database_backend_is_rejected(
        self,
    ):
        engine_builder = MagicMock()

        outcome = check_database_health(
            settings_loader=lambda: (
                self.database_settings()
            ),
            engine_builder=engine_builder,
        )

        self.assertEqual(
            outcome.detail,
            "database_backend_invalid",
        )

        engine_builder.assert_not_called()

    def test_r2_storage_probe_is_healthy(
        self,
    ):
        storage = MagicMock()

        storage.exists.return_value = False

        outcome = check_document_storage_health(
            settings_loader=lambda: (
                self.storage_settings(
                    r2=True
                )
            ),
            storage_loader=lambda: storage,
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "r2_reachable",
        )

        storage.exists.assert_called_once_with(
            SYSTEM_HEALTH_STORAGE_PROBE_KEY
        )

    def test_local_storage_probe_is_healthy(
        self,
    ):
        storage = MagicMock()

        outcome = check_document_storage_health(
            settings_loader=lambda: (
                self.storage_settings(
                    local=True
                )
            ),
            storage_loader=lambda: storage,
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "local_storage_reachable",
        )

    def test_storage_failure_is_sanitized(
        self,
    ):
        storage = MagicMock()

        storage.exists.side_effect = (
            RuntimeError(
                "R2 credential secret"
            )
        )

        outcome = check_document_storage_health(
            settings_loader=lambda: (
                self.storage_settings(
                    r2=True
                )
            ),
            storage_loader=lambda: storage,
        )

        self.assertEqual(
            outcome.status,
            "unavailable",
        )
        self.assertEqual(
            outcome.detail,
            "storage_unreachable",
        )

    def test_invalid_storage_backend_is_rejected(
        self,
    ):
        storage_loader = MagicMock()

        outcome = check_document_storage_health(
            settings_loader=lambda: (
                self.storage_settings()
            ),
            storage_loader=storage_loader,
        )

        self.assertEqual(
            outcome.detail,
            "storage_backend_invalid",
        )

        storage_loader.assert_not_called()

    def test_missing_storage_exists_method_is_rejected(
        self,
    ):
        outcome = check_document_storage_health(
            settings_loader=lambda: (
                self.storage_settings(
                    r2=True
                )
            ),
            storage_loader=lambda: object(),
        )

        self.assertEqual(
            outcome.detail,
            "storage_interface_invalid",
        )

    def test_missing_recovery_report_is_initializing(
        self,
    ):
        outcome = check_document_recovery_health(
            None
        )

        self.assertEqual(
            outcome.status,
            "degraded",
        )
        self.assertEqual(
            outcome.detail,
            "recovery_initializing",
        )

    def test_disabled_recovery_is_healthy_disabled(
        self,
    ):
        report = SimpleNamespace(
            status="disabled",
            enabled=False,
            failure_count=0,
        )

        outcome = check_document_recovery_health(
            report
        )

        self.assertEqual(
            outcome.status,
            "disabled",
        )
        self.assertTrue(
            outcome.healthy
        )

    def test_completed_recovery_is_healthy(
        self,
    ):
        report = SimpleNamespace(
            status="completed",
            enabled=True,
            failure_count=0,
        )

        outcome = check_document_recovery_health(
            report
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "recovery_completed",
        )

    def test_lock_contention_recovery_is_healthy(
        self,
    ):
        report = SimpleNamespace(
            status="skipped_lock_held",
            enabled=True,
            failure_count=0,
        )

        outcome = check_document_recovery_health(
            report
        )

        self.assertEqual(
            outcome.status,
            "healthy",
        )
        self.assertEqual(
            outcome.detail,
            "recovery_lock_held",
        )

    def test_recovery_failures_are_degraded(
        self,
    ):
        report = SimpleNamespace(
            status="completed_with_failures",
            enabled=True,
            failure_count=2,
        )

        outcome = check_document_recovery_health(
            report
        )

        self.assertEqual(
            outcome.status,
            "degraded",
        )
        self.assertEqual(
            outcome.detail,
            "recovery_failures",
        )

    def test_failed_recovery_is_unavailable(
        self,
    ):
        report = SimpleNamespace(
            status="failed",
            enabled=True,
            failure_count=0,
        )

        outcome = check_document_recovery_health(
            report
        )

        self.assertEqual(
            outcome.status,
            "unavailable",
        )
        self.assertEqual(
            outcome.detail,
            "recovery_failed",
        )

    def test_default_definitions_have_stable_order(
        self,
    ):
        database_check = MagicMock(
            return_value=healthy_outcome()
        )

        storage_check = MagicMock(
            return_value=healthy_outcome()
        )

        report = SimpleNamespace(
            status="completed",
            enabled=True,
            failure_count=0,
        )

        definitions = (
            build_default_health_check_definitions(
                recovery_report_provider=(
                    lambda: report
                ),
                database_check=database_check,
                storage_check=storage_check,
            )
        )

        self.assertEqual(
            [
                definition.name
                for definition in definitions
            ],
            [
                "database",
                "document_storage",
                "document_recovery",
            ],
        )

        self.assertEqual(
            [
                definition.critical
                for definition in definitions
            ],
            [
                True,
                True,
                False,
            ],
        )

        self.assertEqual(
            definitions[2].check().status,
            "healthy",
        )

    def test_invalid_recovery_provider_is_rejected(
        self,
    ):
        with self.assertRaises(
            SystemHealthConfigurationError
        ):
            build_default_health_check_definitions(
                recovery_report_provider=None,
            )


if __name__ == "__main__":
    unittest.main()
