import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.dashboard_service import (
    DashboardMetricsError,
    build_dashboard_health,
    build_dashboard_summary,
    summarize_usage_metrics,
)
from app.services.system_health_service import (
    HealthCheckDefinition,
    healthy_outcome,
)


class DashboardServiceTests(
    unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = (
            Path(
                self.temporary_directory.name
            )
            / "dashboard.db"
        )
        self._create_database()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def connection_factory(
        self,
        db_path,
    ):
        return sqlite3.connect(
            str(db_path)
        )

    def _create_database(self):
        connection = sqlite3.connect(
            str(self.database_path)
        )
        cursor = connection.cursor()

        cursor.executescript(
            """
            CREATE TABLE chats (
                id INTEGER PRIMARY KEY
            );

            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                agent_id TEXT DEFAULT NULL
            );

            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                file_size INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            """
        )

        cursor.executemany(
            "INSERT INTO chats (id) VALUES (?)",
            [
                (1,),
                (2,),
                (3,),
            ],
        )

        cursor.executemany(
            """
            INSERT INTO messages (
                id,
                role,
                agent_id
            )
            VALUES (?, ?, ?)
            """,
            [
                (1, "user", None),
                (2, "assistant", "study"),
                (3, "user", None),
                (4, "assistant", "coding"),
                (5, "assistant", "study"),
                (6, "assistant", None),
            ],
        )

        cursor.executemany(
            """
            INSERT INTO documents (
                document_id,
                file_size,
                status
            )
            VALUES (?, ?, ?)
            """,
            [
                ("doc-1", 1024, "ready"),
                ("doc-2", 2048, "processing"),
            ],
        )

        connection.commit()
        connection.close()

    def test_usage_metrics_include_agent_and_storage_counts(self):
        payload = summarize_usage_metrics(
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
        )

        self.assertEqual(
            payload["chats"]["total"],
            3,
        )
        self.assertEqual(
            payload["messages"],
            {
                "total": 6,
                "user": 2,
                "assistant": 4,
            },
        )
        self.assertEqual(
            payload["agents"][
                "assistant_messages_with_agent"
            ],
            3,
        )
        self.assertEqual(
            payload["agents"]["usage"],
            [
                {
                    "agent_id": "study",
                    "message_count": 2,
                },
                {
                    "agent_id": "coding",
                    "message_count": 1,
                },
            ],
        )
        self.assertEqual(
            payload["documents"],
            {
                "total": 2,
                "ready": 1,
            },
        )
        self.assertEqual(
            payload["storage"][
                "document_bytes"
            ],
            3072,
        )

    def test_optional_sections_degrade_without_leaking_failure(self):
        def failing_recovery(
            *args,
            **kwargs,
        ):
            raise RuntimeError(
                "recovery secret"
            )

        def incident_summary(
            *args,
            **kwargs,
        ):
            return {
                "active_count": 2,
            }

        payload = build_dashboard_summary(
            db_path=str(
                self.database_path
            ),
            connection_factory=(
                self.connection_factory
            ),
            recovery_summarizer=(
                failing_recovery
            ),
            incident_summarizer=(
                incident_summary
            ),
        )

        self.assertEqual(
            payload["recovery"],
            {
                "available": False,
                "metrics": None,
            },
        )
        self.assertEqual(
            payload["incidents"],
            {
                "available": True,
                "metrics": {
                    "active_count": 2,
                },
            },
        )
        self.assertNotIn(
            "recovery secret",
            str(payload),
        )

    def test_core_usage_failure_raises_sanitized_error(self):
        def failing_connection(
            db_path,
        ):
            raise RuntimeError(
                "C:/private/database.db"
            )

        with self.assertRaises(
            DashboardMetricsError
        ) as context:
            summarize_usage_metrics(
                db_path=str(
                    self.database_path
                ),
                connection_factory=(
                    failing_connection
                ),
            )

        self.assertEqual(
            str(context.exception),
            (
                "Dashboard usage metrics "
                "are unavailable."
            ),
        )
        self.assertNotIn(
            "private",
            str(context.exception),
        )

    def test_health_reuses_definitions_and_adds_rag_runtime(self):
        recovery_report = object()
        rag_runtime = SimpleNamespace(
            settings=object()
        )

        def definitions_builder(
            *,
            recovery_report_provider,
        ):
            self.assertIs(
                recovery_report_provider(),
                recovery_report,
            )
            return (
                HealthCheckDefinition(
                    name="database",
                    check=lambda: (
                        healthy_outcome(
                            "sqlite_reachable"
                        )
                    ),
                    critical=True,
                ),
                HealthCheckDefinition(
                    name="document_storage",
                    check=lambda: (
                        healthy_outcome(
                            "local_storage_reachable"
                        )
                    ),
                    critical=True,
                ),
                HealthCheckDefinition(
                    name="document_recovery",
                    check=lambda: (
                        healthy_outcome(
                            "recovery_completed"
                        )
                    ),
                    critical=False,
                ),
            )

        payload = build_dashboard_health(
            recovery_report=(
                recovery_report
            ),
            rag_runtime=rag_runtime,
            definitions_builder=(
                definitions_builder
            ),
        )

        self.assertEqual(
            payload["service"],
            "system_health",
        )
        self.assertEqual(
            payload["status"],
            "healthy",
        )
        self.assertEqual(
            [
                component["name"]
                for component in payload[
                    "components"
                ]
            ],
            [
                "database",
                "document_storage",
                "document_recovery",
                "knowledge_rag",
            ],
        )

        rag_component = payload[
            "components"
        ][-1]

        self.assertEqual(
            rag_component["status"],
            "healthy",
        )
        self.assertTrue(
            rag_component["healthy"]
        )
        self.assertFalse(
            rag_component["critical"]
        )
        self.assertEqual(
            rag_component["detail"],
            "rag_runtime_ready",
        )

    def test_missing_rag_runtime_degrades_health(self):
        def definitions_builder(
            *,
            recovery_report_provider,
        ):
            del recovery_report_provider
            return (
                HealthCheckDefinition(
                    name="database",
                    check=healthy_outcome,
                    critical=True,
                ),
            )

        payload = build_dashboard_health(
            rag_runtime=None,
            definitions_builder=(
                definitions_builder
            ),
        )

        self.assertEqual(
            payload["status"],
            "degraded",
        )
        self.assertTrue(
            payload["ready"]
        )
        self.assertTrue(
            payload[
                "attention_required"
            ]
        )
        self.assertEqual(
            payload["components"][-1][
                "detail"
            ],
            "rag_runtime_unavailable",
        )
        self.assertFalse(
            payload["components"][-1][
                "critical"
            ]
        )

    def test_health_failure_raises_sanitized_error(self):
        def failing_runner(
            definitions,
        ):
            del definitions
            raise RuntimeError(
                "postgresql://user:secret@host/db"
            )

        with self.assertRaises(
            DashboardMetricsError
        ) as context:
            build_dashboard_health(
                recovery_report=None,
                rag_runtime=(
                    SimpleNamespace(
                        settings=object()
                    )
                ),
                definitions_builder=(
                    lambda **ignored: ()
                ),
                health_runner=(
                    failing_runner
                ),
            )

        self.assertEqual(
            str(context.exception),
            (
                "Dashboard health metrics "
                "are unavailable."
            ),
        )
        self.assertNotIn(
            "secret",
            str(context.exception),
        )
        self.assertNotIn(
            "postgresql://",
            str(context.exception),
        )


if __name__ == "__main__":
    unittest.main()
