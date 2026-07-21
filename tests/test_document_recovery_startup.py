from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.config.document_recovery import (
    DocumentRecoverySettings,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
    run_document_recovery_startup,
)
from app.services.document_recovery_service import (
    DocumentRecoveryRun,
    DocumentRecoveryScan,
)


def empty_scan(
    *,
    enabled: bool = True,
    total_examined: int = 0,
    recent_count: int = 0,
    invalid_timestamp_count: int = 0,
    deferred_count: int = 0,
) -> DocumentRecoveryScan:
    return DocumentRecoveryScan(
        enabled=enabled,
        total_examined=total_examined,
        recent_count=recent_count,
        invalid_timestamp_count=(
            invalid_timestamp_count
        ),
        deferred_count=deferred_count,
        candidates=(),
    )


def startup_report(
    *,
    status: str = "completed",
) -> DocumentRecoveryStartupReport:
    return DocumentRecoveryStartupReport(
        status=status,
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
    )


class DocumentRecoveryStartupRuntimeTests(
    unittest.TestCase
):
    def test_disabled_runtime_does_not_execute_recovery(
        self,
    ):
        recover = Mock()

        report = run_document_recovery_startup(
            rag=object(),
            settings=DocumentRecoverySettings(
                enabled=False,
                stale_after_seconds=900,
                batch_size=25,
            ),
            recover_fn=recover,
        )

        recover.assert_not_called()

        self.assertEqual(
            report.status,
            "disabled",
        )

        self.assertFalse(
            report.enabled
        )

    def test_successful_runtime_returns_summary(
        self,
    ):
        recover = Mock(
            return_value=DocumentRecoveryRun(
                scan=empty_scan(
                    total_examined=4,
                    recent_count=2,
                    invalid_timestamp_count=1,
                    deferred_count=1,
                ),
                results=(),
            )
        )

        report = run_document_recovery_startup(
            rag=object(),
            settings=DocumentRecoverySettings(
                enabled=True,
                stale_after_seconds=900,
                batch_size=25,
            ),
            recover_fn=recover,
        )

        self.assertEqual(
            report.status,
            "completed",
        )

        self.assertEqual(
            report.total_examined,
            4,
        )

        self.assertEqual(
            report.recent_count,
            2,
        )

        self.assertEqual(
            report.invalid_timestamp_count,
            1,
        )

        self.assertEqual(
            report.deferred_count,
            1,
        )

    def test_runtime_reports_recovery_failures(
        self,
    ):
        result = SimpleNamespace(
            scan=empty_scan(
                total_examined=1,
            ),
            processing_recovered_count=0,
            deleting_completed_count=0,
            failure_count=1,
            skipped_count=0,
        )

        report = run_document_recovery_startup(
            rag=object(),
            settings=DocumentRecoverySettings(
                enabled=True,
                stale_after_seconds=900,
                batch_size=25,
            ),
            recover_fn=Mock(
                return_value=result
            ),
        )

        self.assertEqual(
            report.status,
            "completed_with_failures",
        )

        self.assertEqual(
            report.failure_count,
            1,
        )

    def test_runtime_exception_is_non_fatal(
        self,
    ):
        logger = Mock()

        report = run_document_recovery_startup(
            rag=object(),
            settings=DocumentRecoverySettings(
                enabled=True,
                stale_after_seconds=900,
                batch_size=25,
            ),
            recover_fn=Mock(
                side_effect=RuntimeError(
                    "Database temporarily unavailable"
                )
            ),
            logger=logger,
        )

        self.assertEqual(
            report.status,
            "failed",
        )

        self.assertIn(
            "RuntimeError",
            report.error,
        )

        logger.exception.assert_called_once()

    def test_create_app_executes_recovery_on_startup(
        self,
    ):
        from app import main as main_module

        expected_report = startup_report()
        recovery_runner = Mock(
            return_value=expected_report
        )
        recovery_rag = object()

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
                        enabled=True,
                        stale_after_seconds=900,
                        batch_size=25,
                    )
                ),
                document_recovery_runner=(
                    recovery_runner
                ),
                document_recovery_rag=(
                    recovery_rag
                ),
            )

            self.assertIsNone(
                application.state
                .document_recovery_report
            )

            with TestClient(application):
                pass

        recovery_runner.assert_called_once()

        call = recovery_runner.call_args

        self.assertIs(
            call.kwargs["rag"],
            recovery_rag,
        )

        self.assertIs(
            application.state
            .document_recovery_report,
            expected_report,
        )


if __name__ == "__main__":
    unittest.main()
