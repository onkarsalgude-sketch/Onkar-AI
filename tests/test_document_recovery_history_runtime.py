from __future__ import annotations

import ast
import logging
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from app.services.document_recovery_history_runtime import (
    run_document_recovery_startup_with_history,
)
from app.services.document_recovery_runtime import (
    DocumentRecoveryStartupReport,
)


ROOT = Path(__file__).resolve().parents[1]


def recovery_report(
    *,
    status: str = "completed",
    failure_count: int = 0,
    error: str | None = None,
):
    return DocumentRecoveryStartupReport(
        status=status,
        enabled=(
            status != "disabled"
        ),
        total_examined=2,
        candidate_count=1,
        processing_recovered_count=1,
        deleting_completed_count=0,
        failure_count=failure_count,
        skipped_count=0,
        recent_count=1,
        invalid_timestamp_count=0,
        deferred_count=0,
        error=error,
    )


class DocumentRecoveryHistoryRuntimeTests(
    unittest.TestCase
):
    def test_successful_run_is_recorded_once(
        self,
    ):
        report = recovery_report()

        runner = MagicMock(
            return_value=report
        )

        recorder = MagicMock()

        wall_clock = iter(
            (
                datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    1,
                    tzinfo=timezone.utc,
                ),
            )
        )

        monotonic_clock = iter(
            (
                100.0,
                100.125,
            )
        )

        returned = (
            run_document_recovery_startup_with_history(
                rag="rag-runtime",
                settings="settings-runtime",
                now=datetime(
                    2026,
                    7,
                    21,
                    9,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                recovery_runner=runner,
                history_recorder=recorder,
                utc_now_fn=lambda: next(
                    wall_clock
                ),
                monotonic_fn=lambda: next(
                    monotonic_clock
                ),
            )
        )

        self.assertIs(
            returned,
            report,
        )

        runner.assert_called_once()

        runner_arguments = (
            runner.call_args.kwargs
        )

        self.assertEqual(
            runner_arguments["rag"],
            "rag-runtime",
        )

        self.assertEqual(
            runner_arguments["settings"],
            "settings-runtime",
        )

        recorder.assert_called_once()

        recorder_arguments = (
            recorder.call_args.kwargs
        )

        self.assertEqual(
            recorder.call_args.args,
            (
                report,
            ),
        )

        self.assertEqual(
            recorder_arguments[
                "duration_ms"
            ],
            125,
        )

        self.assertEqual(
            recorder_arguments[
                "started_at"
            ],
            datetime(
                2026,
                7,
                21,
                10,
                0,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            recorder_arguments[
                "finished_at"
            ],
            datetime(
                2026,
                7,
                21,
                10,
                0,
                1,
                tzinfo=timezone.utc,
            ),
        )

    def test_all_report_statuses_are_forwarded(
        self,
    ):
        statuses = (
            "disabled",
            "completed",
            "completed_with_failures",
            "skipped_lock_held",
            "failed",
        )

        recorder = MagicMock()

        for index, status in enumerate(
            statuses
        ):
            with self.subTest(
                status=status
            ):
                report = recovery_report(
                    status=status,
                    failure_count=(
                        1
                        if status
                        in {
                            "failed",
                            "completed_with_failures",
                        }
                        else 0
                    ),
                    error=(
                        "SECRET runtime error"
                        if status == "failed"
                        else None
                    ),
                )

                wall_clock = iter(
                    (
                        datetime(
                            2026,
                            7,
                            21,
                            10,
                            0,
                            index,
                            tzinfo=timezone.utc,
                        ),
                        datetime(
                            2026,
                            7,
                            21,
                            10,
                            0,
                            index,
                            tzinfo=timezone.utc,
                        ),
                    )
                )

                ticks = iter(
                    (
                        float(index),
                        float(index),
                    )
                )

                returned = (
                    run_document_recovery_startup_with_history(
                        rag=None,
                        recovery_runner=(
                            lambda **ignored: report
                        ),
                        history_recorder=recorder,
                        utc_now_fn=lambda: next(
                            wall_clock
                        ),
                        monotonic_fn=lambda: next(
                            ticks
                        ),
                    )
                )

                self.assertIs(
                    returned,
                    report,
                )

        self.assertEqual(
            recorder.call_count,
            len(statuses),
        )

        recorded_reports = [
            call.args[0]
            for call in recorder.call_args_list
        ]

        self.assertEqual(
            [
                report.status
                for report in recorded_reports
            ],
            list(statuses),
        )

    def test_history_failure_is_nonfatal_and_generic(
        self,
    ):
        report = recovery_report()

        logger = MagicMock(
            spec=logging.Logger
        )

        def failing_recorder(
            *args,
            **kwargs,
        ):
            raise RuntimeError(
                "SECRET database URL"
            )

        times = iter(
            (
                datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    1,
                    tzinfo=timezone.utc,
                ),
            )
        )

        ticks = iter(
            (
                1.0,
                2.0,
            )
        )

        returned = (
            run_document_recovery_startup_with_history(
                rag=None,
                recovery_runner=(
                    lambda **ignored: report
                ),
                history_recorder=(
                    failing_recorder
                ),
                utc_now_fn=lambda: next(
                    times
                ),
                monotonic_fn=lambda: next(
                    ticks
                ),
                logger=logger,
            )
        )

        self.assertIs(
            returned,
            report,
        )

        logger.warning.assert_called_once_with(
            "Document recovery history "
            "persistence failed."
        )

        self.assertNotIn(
            "SECRET",
            repr(
                logger.warning.call_args
            ),
        )

    def test_clock_regression_is_clamped(
        self,
    ):
        report = recovery_report()

        recorder = MagicMock()

        times = iter(
            (
                datetime(
                    2026,
                    7,
                    21,
                    11,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
            )
        )

        ticks = iter(
            (
                20.0,
                19.0,
            )
        )

        run_document_recovery_startup_with_history(
            rag=None,
            recovery_runner=(
                lambda **ignored: report
            ),
            history_recorder=recorder,
            utc_now_fn=lambda: next(
                times
            ),
            monotonic_fn=lambda: next(
                ticks
            ),
        )

        recorder_arguments = (
            recorder.call_args.kwargs
        )

        self.assertEqual(
            recorder_arguments[
                "finished_at"
            ],
            recorder_arguments[
                "started_at"
            ],
        )

        self.assertEqual(
            recorder_arguments[
                "duration_ms"
            ],
            0,
        )

    def test_runner_failure_propagates_without_record(
        self,
    ):
        recorder = MagicMock()

        def failing_runner(
            **ignored,
        ):
            raise RuntimeError(
                "Recovery runner failed"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "Recovery runner failed",
        ):
            run_document_recovery_startup_with_history(
                rag=None,
                recovery_runner=(
                    failing_runner
                ),
                history_recorder=recorder,
                utc_now_fn=lambda: datetime(
                    2026,
                    7,
                    21,
                    10,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                monotonic_fn=lambda: 1.0,
            )

        recorder.assert_not_called()

    def test_main_default_symbol_uses_wrapper_alias(
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

        wrapper_alias_found = False

        for node in tree.body:
            if not isinstance(
                node,
                ast.ImportFrom,
            ):
                continue

            if (
                node.module
                != (
                    "app.services."
                    "document_recovery_history_runtime"
                )
            ):
                continue

            for alias in node.names:
                if (
                    alias.name
                    == (
                        "run_document_recovery_"
                        "startup_with_history"
                    )
                    and alias.asname
                    == (
                        "run_document_recovery_startup"
                    )
                ):
                    wrapper_alias_found = True

        self.assertTrue(
            wrapper_alias_found
        )


if __name__ == "__main__":
    unittest.main()
