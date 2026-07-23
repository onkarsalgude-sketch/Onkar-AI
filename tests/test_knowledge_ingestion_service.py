import hashlib
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from app.services import (
    knowledge_ingestion_service,
)
from app.services.knowledge_service import (
    KnowledgeMetadataConflictError,
    KnowledgeMetadataError,
)


PDF_BYTES = (
    b"%PDF-1.7\n"
    b"durable knowledge ingestion"
)
FILE_HASH = hashlib.sha256(
    PDF_BYTES
).hexdigest()


def processing_record(
    *,
    knowledge_id="knowledge-1",
    title="Guide",
    filename="Guide.pdf",
    object_key=None,
):
    return {
        "knowledge_id": knowledge_id,
        "title": title,
        "filename": filename,
        "object_key": (
            object_key
            or (
                "knowledge/documents/"
                f"{knowledge_id}/"
                f"{FILE_HASH}/"
                f"{filename}"
            )
        ),
        "file_hash": FILE_HASH,
        "file_size": len(PDF_BYTES),
        "page_count": 0,
        "chunk_count": 0,
        "status": "processing",
        "is_enabled": True,
        "created_at": (
            "2026-07-22T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-22T00:00:00+00:00"
        ),
    }


def ready_record():
    record = processing_record()
    record.update(
        {
            "page_count": 3,
            "chunk_count": 7,
            "status": "ready",
            "updated_at": (
                "2026-07-22T00:01:00+00:00"
            ),
        }
    )
    return record


@contextmanager
def fake_materialize(
    data,
    filename,
):
    if data != PDF_BYTES:
        raise AssertionError(
            "unexpected PDF bytes"
        )

    yield Path(
        "C:/temp"
    ) / filename


class FakeRAG:
    def __init__(
        self,
        *,
        fail_index=False,
        fail_delete=False,
        events=None,
    ):
        self.fail_index = fail_index
        self.fail_delete = fail_delete
        self.events = (
            events
            if events is not None
            else []
        )
        self.index_calls = []
        self.delete_calls = []

    def index_pdf(
        self,
        *,
        file_path,
        knowledge_id,
    ):
        self.events.append("index")
        self.index_calls.append(
            {
                "file_path": file_path,
                "knowledge_id": (
                    knowledge_id
                ),
            }
        )

        if self.fail_index:
            raise RuntimeError(
                "vector://private-index"
            )

        return {
            "knowledge_id": (
                knowledge_id
            ),
            "filename": (
                Path(file_path).name
            ),
            "pages": 3,
            "chunks": 7,
        }

    def delete_document(
        self,
        *,
        knowledge_id,
        filename,
    ):
        self.events.append(
            "delete_vectors"
        )
        self.delete_calls.append(
            {
                "knowledge_id": (
                    knowledge_id
                ),
                "filename": filename,
            }
        )

        if self.fail_delete:
            raise RuntimeError(
                "vector://private-delete"
            )

        return {
            "knowledge_id": (
                knowledge_id
            ),
            "filename": filename,
            "deleted_chunks": 7,
            "remaining_chunks": 0,
        }


class KnowledgeIngestionServiceTests(
    unittest.TestCase
):
    def dependencies(
        self,
        *,
        rag=None,
        events=None,
    ):
        resolved_events = (
            events
            if events is not None
            else []
        )
        resolved_rag = (
            rag
            if rag is not None
            else FakeRAG(
                events=resolved_events
            )
        )
        object_key = (
            "knowledge/documents/"
            "knowledge-1/"
            f"{FILE_HASH}/"
            "Guide.pdf"
        )

        def store_pdf_fn(**kwargs):
            resolved_events.append(
                "store_object"
            )
            self.assertEqual(
                kwargs["file_hash"],
                FILE_HASH,
            )
            return object_key

        def create_metadata_fn(
            **kwargs,
        ):
            resolved_events.append(
                "create_metadata"
            )
            return processing_record(
                object_key=object_key
            )

        def update_status_fn(
            knowledge_id,
            status,
            **kwargs,
        ):
            resolved_events.append(
                f"status_{status}"
            )

            if status == "ready":
                self.assertEqual(
                    kwargs,
                    {
                        "page_count": 3,
                        "chunk_count": 7,
                    },
                )
                return ready_record()

            return {
                **processing_record(
                    object_key=(
                        object_key
                    )
                ),
                "status": status,
            }

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
            "rag": resolved_rag,
            "events": resolved_events,
            "store_pdf_fn": (
                store_pdf_fn
            ),
            "create_metadata_fn": (
                create_metadata_fn
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
            "materialize_fn": (
                fake_materialize
            ),
        }

    def ingest(self, deps, **overrides):
        arguments = {
            "title": " Guide ",
            "filename": "../Guide.pdf",
            "data": PDF_BYTES,
            "knowledge_id": (
                "knowledge-1"
            ),
            "rag": deps["rag"],
            "store_pdf_fn": (
                deps["store_pdf_fn"]
            ),
            "create_metadata_fn": (
                deps[
                    "create_metadata_fn"
                ]
            ),
            "update_status_fn": (
                deps["update_status_fn"]
            ),
            "delete_object_fn": (
                deps["delete_object_fn"]
            ),
            "delete_metadata_fn": (
                deps[
                    "delete_metadata_fn"
                ]
            ),
            "materialize_fn": (
                deps["materialize_fn"]
            ),
        }
        arguments.update(overrides)

        return (
            knowledge_ingestion_service
            .ingest_knowledge_pdf(
                **arguments
            )
        )

    def test_successful_ingestion_order_and_safe_result(
        self,
    ):
        deps = self.dependencies()

        result = self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "index",
                "status_ready",
            ],
        )
        self.assertEqual(
            result,
            {
                "knowledge_id": (
                    "knowledge-1"
                ),
                "title": "Guide",
                "filename": "Guide.pdf",
                "file_size": len(
                    PDF_BYTES
                ),
                "page_count": 3,
                "chunk_count": 7,
                "status": "ready",
                "is_enabled": True,
                "created_at": (
                    "2026-07-22"
                    "T00:00:00+00:00"
                ),
                "updated_at": (
                    "2026-07-22"
                    "T00:01:00+00:00"
                ),
            },
        )
        self.assertNotIn(
            "object_key",
            result,
        )
        self.assertNotIn(
            "file_hash",
            result,
        )

    def test_validation_stops_before_side_effects(
        self,
    ):
        dependencies = {
            "rag_factory": Mock(),
            "store_pdf_fn": Mock(),
            "create_metadata_fn": Mock(),
        }
        invalid_requests = (
            {
                "title": "",
                "filename": "Guide.pdf",
                "data": PDF_BYTES,
            },
            {
                "title": "Guide",
                "filename": "Guide.txt",
                "data": PDF_BYTES,
            },
            {
                "title": "Guide",
                "filename": "Guide.pdf",
                "data": b"not a pdf",
            },
            {
                "title": "Guide",
                "filename": "Guide.pdf",
                "data": (
                    b"%PDF-1.7\n"
                    + b"x"
                    * (
                        knowledge_ingestion_service
                        .MAX_KNOWLEDGE_PDF_BYTES
                    )
                ),
            },
        )

        for request in invalid_requests:
            with self.subTest(
                request=request
            ):
                with self.assertRaises(
                    knowledge_ingestion_service
                    .KnowledgeIngestionValidationError
                ):
                    (
                        knowledge_ingestion_service
                        .ingest_knowledge_pdf(
                            **request,
                            **dependencies,
                        )
                    )

        dependencies[
            "rag_factory"
        ].assert_not_called()
        dependencies[
            "store_pdf_fn"
        ].assert_not_called()
        dependencies[
            "create_metadata_fn"
        ].assert_not_called()

    def test_id_factory_runs_before_side_effects(
        self,
    ):
        deps = self.dependencies()
        id_factory = Mock(
            return_value="knowledge-1"
        )

        self.ingest(
            deps,
            knowledge_id=None,
            id_factory=id_factory,
        )

        id_factory.assert_called_once_with()

    def test_duplicate_conflict_removes_object(
        self,
    ):
        deps = self.dependencies()

        def conflict(**kwargs):
            deps["events"].append(
                "create_metadata"
            )
            raise (
                KnowledgeMetadataConflictError(
                    "postgresql://secret"
                )
            )

        deps[
            "create_metadata_fn"
        ] = conflict

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionConflictError
        ) as captured:
            self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "delete_object",
            ],
        )
        self.assertNotIn(
            "secret",
            str(captured.exception),
        )

    def test_metadata_failure_removes_object_and_possible_row(
        self,
    ):
        deps = self.dependencies()

        def fail(**kwargs):
            deps["events"].append(
                "create_metadata"
            )
            raise KnowledgeMetadataError(
                "sqlite:///private"
            )

        deps[
            "create_metadata_fn"
        ] = fail

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "delete_object",
                "delete_metadata",
            ],
        )

    def test_index_failure_cleans_in_resumable_order(
        self,
    ):
        events = []
        rag = FakeRAG(
            fail_index=True,
            events=events,
        )
        deps = self.dependencies(
            rag=rag,
            events=events,
        )

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ) as captured:
            self.ingest(deps)

        self.assertEqual(
            events,
            [
                "store_object",
                "create_metadata",
                "index",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )
        self.assertNotIn(
            "private",
            str(captured.exception),
        )

    def test_ready_status_failure_cleans_every_layer(
        self,
    ):
        deps = self.dependencies()

        def fail_status(
            knowledge_id,
            status,
            **kwargs,
        ):
            deps["events"].append(
                f"status_{status}"
            )

            if status == "ready":
                raise KnowledgeMetadataError(
                    "postgresql://private"
                )

            return {
                **processing_record(),
                "status": "failed",
            }

        deps[
            "update_status_fn"
        ] = fail_status

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "index",
                "status_ready",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )

    def test_vector_cleanup_failure_preserves_durable_state(
        self,
    ):
        events = []
        rag = FakeRAG(
            fail_index=True,
            fail_delete=True,
            events=events,
        )
        deps = self.dependencies(
            rag=rag,
            events=events,
        )

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            events,
            [
                "store_object",
                "create_metadata",
                "index",
                "delete_vectors",
                "status_failed",
            ],
        )

    def test_object_cleanup_failure_preserves_metadata(
        self,
    ):
        events = []
        rag = FakeRAG(
            fail_index=True,
            events=events,
        )
        deps = self.dependencies(
            rag=rag,
            events=events,
        )

        def fail_delete_object(
            record,
            *,
            storage,
        ):
            events.append(
                "delete_object"
            )
            raise RuntimeError(
                "r2://private"
            )

        deps[
            "delete_object_fn"
        ] = fail_delete_object

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            events,
            [
                "store_object",
                "create_metadata",
                "index",
                "delete_vectors",
                "delete_object",
                "status_failed",
            ],
        )

    def test_invalid_metadata_result_is_cleaned(
        self,
    ):
        deps = self.dependencies()

        def invalid(**kwargs):
            deps["events"].append(
                "create_metadata"
            )
            record = processing_record()
            record["file_hash"] = "b" * 64
            return record

        deps[
            "create_metadata_fn"
        ] = invalid

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )

    def test_none_ready_result_is_cleaned(
        self,
    ):
        deps = self.dependencies()

        def missing(
            knowledge_id,
            status,
            **kwargs,
        ):
            deps["events"].append(
                f"status_{status}"
            )

            if status == "ready":
                return None

            return {
                **processing_record(),
                "status": status,
            }

        deps[
            "update_status_fn"
        ] = missing

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ):
            self.ingest(deps)

        self.assertEqual(
            deps["events"],
            [
                "store_object",
                "create_metadata",
                "index",
                "status_ready",
                "delete_vectors",
                "delete_object",
                "delete_metadata",
            ],
        )

    def test_rag_factory_failure_has_no_side_effects(
        self,
    ):
        rag_factory = Mock(
            side_effect=RuntimeError(
                "vector://private"
            )
        )
        store = Mock()

        with self.assertRaises(
            knowledge_ingestion_service
            .KnowledgeIngestionError
        ) as captured:
            (
                knowledge_ingestion_service
                .ingest_knowledge_pdf(
                    title="Guide",
                    filename="Guide.pdf",
                    data=PDF_BYTES,
                    knowledge_id=(
                        "knowledge-1"
                    ),
                    rag_factory=(
                        rag_factory
                    ),
                    store_pdf_fn=store,
                )
            )

        store.assert_not_called()
        self.assertNotIn(
            "private",
            str(captured.exception),
        )


if __name__ == "__main__":
    unittest.main()
