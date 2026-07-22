import unittest
from unittest.mock import Mock

from app.services import (
    knowledge_delete_service,
)


OBJECT_KEY = (
    "knowledge/documents/"
    "knowledge-1/"
    + ("a" * 64)
    + "/Guide.pdf"
)


def record_fixture(
    *,
    status="ready",
    object_key=OBJECT_KEY,
    filename="Guide.pdf",
    knowledge_id="knowledge-1",
):
    return {
        "knowledge_id": knowledge_id,
        "title": "Guide",
        "filename": filename,
        "object_key": object_key,
        "file_hash": "a" * 64,
        "file_size": 100,
        "page_count": 3,
        "chunk_count": 7,
        "status": status,
        "is_enabled": True,
        "created_at": (
            "2026-07-22T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-22T00:01:00+00:00"
        ),
    }


class FakeRAG:
    def __init__(
        self,
        *,
        events,
        fail_delete=False,
    ):
        self.events = events
        self.fail_delete = fail_delete
        self.calls = []

    def delete_document(
        self,
        *,
        knowledge_id,
        filename,
    ):
        self.events.append(
            "delete_vectors"
        )
        self.calls.append(
            {
                "knowledge_id": (
                    knowledge_id
                ),
                "filename": filename,
            }
        )

        if self.fail_delete:
            raise RuntimeError(
                "vector://private"
            )

        return {
            "knowledge_id": (
                knowledge_id
            ),
            "filename": filename,
            "deleted_chunks": 7,
            "remaining_chunks": 0,
        }


class KnowledgeDeleteServiceTests(
    unittest.TestCase
):
    def dependencies(
        self,
        *,
        current=None,
        events=None,
        rag=None,
    ):
        resolved_events = (
            events
            if events is not None
            else []
        )
        current_record = (
            record_fixture()
            if current is None
            else current
        )
        resolved_rag = (
            rag
            if rag is not None
            else FakeRAG(
                events=resolved_events
            )
        )

        def get_metadata_fn(
            knowledge_id,
        ):
            resolved_events.append(
                "get_metadata"
            )
            return current_record

        def update_status_fn(
            knowledge_id,
            status,
        ):
            resolved_events.append(
                f"status_{status}"
            )
            return record_fixture(
                status=status
            )

        def delete_object_fn(
            record,
            *,
            storage,
        ):
            resolved_events.append(
                "delete_object"
            )
            return True

        def delete_metadata_fn(
            knowledge_id,
        ):
            resolved_events.append(
                "delete_metadata"
            )
            return True

        return {
            "events": resolved_events,
            "rag": resolved_rag,
            "get_metadata_fn": (
                get_metadata_fn
            ),
            "update_status_fn": (
                update_status_fn
            ),
            "delete_object_fn": (
                delete_object_fn
            ),
            "delete_metadata_fn": (
                delete_metadata_fn
            ),
        }

    def delete(self, deps, **overrides):
        arguments = {
            "knowledge_id": (
                "knowledge-1"
            ),
            "rag": deps["rag"],
            "get_metadata_fn": (
                deps["get_metadata_fn"]
            ),
            "update_status_fn": (
                deps["update_status_fn"]
            ),
            "delete_object_fn": (
                deps["delete_object_fn"]
            ),
            "delete_metadata_fn": (
                deps["delete_metadata_fn"]
            ),
        }
        arguments.update(overrides)

        return (
            knowledge_delete_service
            .delete_knowledge_pdf(
                **arguments
            )
        )

    def test_success_uses_resumable_order(
        self,
    ):
        deps = self.dependencies()

        result = self.delete(deps)

        self.assertEqual(
            deps["events"],
            [
                "get_metadata",
                "status_deleting",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )
        self.assertEqual(
            result,
            {
                "knowledge_id": (
                    "knowledge-1"
                ),
                "deleted": True,
            },
        )

    def test_missing_metadata_is_idempotent(
        self,
    ):
        events = []

        def missing(knowledge_id):
            events.append(
                "get_metadata"
            )
            return None

        result = (
            knowledge_delete_service
            .delete_knowledge_pdf(
                "knowledge-1",
                get_metadata_fn=missing,
                rag_factory=Mock(),
                update_status_fn=Mock(),
                delete_object_fn=Mock(),
                delete_metadata_fn=Mock(),
            )
        )

        self.assertEqual(
            result,
            {
                "knowledge_id": (
                    "knowledge-1"
                ),
                "deleted": False,
            },
        )
        self.assertEqual(
            events,
            ["get_metadata"],
        )

    def test_invalid_request_stops_before_reads(
        self,
    ):
        reader = Mock()

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteValidationError
        ):
            (
                knowledge_delete_service
                .delete_knowledge_pdf(
                    "../unsafe",
                    get_metadata_fn=reader,
                )
            )

        reader.assert_not_called()

    def test_invalid_record_stops_before_status_change(
        self,
    ):
        deps = self.dependencies(
            current=record_fixture(
                object_key=(
                    "chats/7/documents/"
                    "private.pdf"
                )
            )
        )

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ):
            self.delete(deps)

        self.assertEqual(
            deps["events"],
            ["get_metadata"],
        )

    def test_rag_factory_failure_precedes_status_change(
        self,
    ):
        events = []

        def get_metadata(knowledge_id):
            events.append(
                "get_metadata"
            )
            return record_fixture()

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ) as captured:
            (
                knowledge_delete_service
                .delete_knowledge_pdf(
                    "knowledge-1",
                    get_metadata_fn=(
                        get_metadata
                    ),
                    rag_factory=Mock(
                        side_effect=RuntimeError(
                            "vector://private"
                        )
                    ),
                    update_status_fn=Mock(),
                )
            )

        self.assertEqual(
            events,
            ["get_metadata"],
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )

    def test_status_race_is_idempotent(
        self,
    ):
        deps = self.dependencies()

        def missing_update(
            knowledge_id,
            status,
        ):
            deps["events"].append(
                f"status_{status}"
            )
            return None

        deps[
            "update_status_fn"
        ] = missing_update

        result = self.delete(deps)

        self.assertFalse(
            result["deleted"]
        )
        self.assertEqual(
            deps["events"],
            [
                "get_metadata",
                "status_deleting",
            ],
        )

    def test_vector_failure_preserves_object_and_metadata(
        self,
    ):
        events = []
        rag = FakeRAG(
            events=events,
            fail_delete=True,
        )
        deps = self.dependencies(
            events=events,
            rag=rag,
        )

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ) as captured:
            self.delete(deps)

        self.assertEqual(
            events,
            [
                "get_metadata",
                "status_deleting",
                "delete_vectors",
            ],
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )

    def test_object_failure_preserves_metadata(
        self,
    ):
        deps = self.dependencies()

        def fail_object(
            record,
            *,
            storage,
        ):
            deps["events"].append(
                "delete_object"
            )
            raise RuntimeError(
                "r2://private"
            )

        deps[
            "delete_object_fn"
        ] = fail_object

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ):
            self.delete(deps)

        self.assertEqual(
            deps["events"],
            [
                "get_metadata",
                "status_deleting",
                "delete_vectors",
                "delete_object",
            ],
        )

    def test_missing_object_allows_metadata_cleanup(
        self,
    ):
        deps = self.dependencies(
            current=record_fixture(
                status="deleting"
            )
        )

        def missing_object(
            record,
            *,
            storage,
        ):
            deps["events"].append(
                "delete_object"
            )
            return False

        deps[
            "delete_object_fn"
        ] = missing_object

        result = self.delete(deps)

        self.assertTrue(
            result["deleted"]
        )
        self.assertEqual(
            deps["events"][-2:],
            [
                "delete_object",
                "delete_metadata",
            ],
        )

    def test_metadata_failure_remains_retryable(
        self,
    ):
        deps = self.dependencies()

        def fail_metadata(
            knowledge_id,
        ):
            deps["events"].append(
                "delete_metadata"
            )
            raise RuntimeError(
                "postgresql://private"
            )

        deps[
            "delete_metadata_fn"
        ] = fail_metadata

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ) as captured:
            self.delete(deps)

        self.assertEqual(
            deps["events"],
            [
                "get_metadata",
                "status_deleting",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )

    def test_deleting_record_mismatch_stops_before_layers(
        self,
    ):
        deps = self.dependencies()

        def mismatch(
            knowledge_id,
            status,
        ):
            deps["events"].append(
                f"status_{status}"
            )
            return record_fixture(
                status="deleting",
                filename="Other.pdf",
            )

        deps[
            "update_status_fn"
        ] = mismatch

        with self.assertRaises(
            knowledge_delete_service
            .KnowledgeDeleteError
        ):
            self.delete(deps)

        self.assertEqual(
            deps["events"],
            [
                "get_metadata",
                "status_deleting",
            ],
        )


if __name__ == "__main__":
    unittest.main()
