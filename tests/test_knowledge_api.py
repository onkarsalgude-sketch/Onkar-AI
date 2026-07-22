import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import knowledge as knowledge_api
from app.services.knowledge_service import (
    KnowledgeMetadataConflictError,
    KnowledgeMetadataError,
)


INTERNAL_OBJECT_KEY = (
    "knowledge/private/operating-guide.pdf"
)
INTERNAL_FILE_HASH = "a" * 64


def record_fixture(
    *,
    knowledge_id="knowledge-1",
    status="processing",
    is_enabled=True,
    page_count=0,
    chunk_count=0,
):
    return {
        "knowledge_id": knowledge_id,
        "title": "Operating Guide",
        "filename": "operating-guide.pdf",
        "object_key": INTERNAL_OBJECT_KEY,
        "file_hash": INTERNAL_FILE_HASH,
        "file_size": 1024,
        "page_count": page_count,
        "chunk_count": chunk_count,
        "status": status,
        "is_enabled": is_enabled,
        "created_at": (
            "2026-07-22T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-22T00:00:00+00:00"
        ),
    }


def client() -> TestClient:
    application = FastAPI()
    application.include_router(
        knowledge_api.router
    )
    return TestClient(application)


class KnowledgeMetadataApiTests(
    unittest.TestCase
):
    def test_create_returns_sanitized_record(
        self,
    ):
        with patch.object(
            knowledge_api,
            "create_metadata_record",
            return_value=record_fixture(),
        ) as creator:
            response = client().post(
                "/knowledge",
                json={
                    "title": "Operating Guide",
                    "filename": (
                        "../operating-guide.pdf"
                    ),
                    "object_key": (
                        INTERNAL_OBJECT_KEY
                    ),
                    "file_hash": (
                        INTERNAL_FILE_HASH
                    ),
                    "file_size": 1024,
                },
            )

        self.assertEqual(
            response.status_code,
            201,
        )
        self.assertEqual(
            response.headers[
                "cache-control"
            ],
            "private, no-store",
        )
        self.assertEqual(
            response.headers[
                "x-content-type-options"
            ],
            "nosniff",
        )
        payload = response.json()

        self.assertEqual(
            payload["knowledge_id"],
            "knowledge-1",
        )
        self.assertEqual(
            payload["filename"],
            "operating-guide.pdf",
        )
        self.assertNotIn(
            "object_key",
            payload,
        )
        self.assertNotIn(
            "file_hash",
            payload,
        )
        self.assertNotIn(
            INTERNAL_OBJECT_KEY,
            response.text,
        )
        self.assertNotIn(
            INTERNAL_FILE_HASH,
            response.text,
        )

        creator.assert_called_once_with(
            title="Operating Guide",
            filename="operating-guide.pdf",
            object_key=INTERNAL_OBJECT_KEY,
            file_hash=INTERNAL_FILE_HASH,
            file_size=1024,
        )

    def test_invalid_create_is_rejected_before_service(
        self,
    ):
        with patch.object(
            knowledge_api,
            "create_metadata_record",
        ) as creator:
            response = client().post(
                "/knowledge",
                json={
                    "title": "",
                    "filename": "report.pdf",
                    "object_key": (
                        "knowledge/report.pdf"
                    ),
                    "file_hash": "unsafe",
                    "file_size": -1,
                },
            )

        self.assertEqual(
            response.status_code,
            400,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Invalid knowledge request"
                )
            },
        )
        creator.assert_not_called()

    def test_conflict_is_stable_and_sanitized(
        self,
    ):
        with patch.object(
            knowledge_api,
            "create_metadata_record",
            side_effect=(
                KnowledgeMetadataConflictError(
                    "sqlite UNIQUE failure "
                    + INTERNAL_OBJECT_KEY
                )
            ),
        ):
            response = client().post(
                "/knowledge",
                json={
                    "title": "Operating Guide",
                    "filename": "guide.pdf",
                    "object_key": (
                        INTERNAL_OBJECT_KEY
                    ),
                    "file_hash": (
                        INTERNAL_FILE_HASH
                    ),
                    "file_size": 1,
                },
            )

        self.assertEqual(
            response.status_code,
            409,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Knowledge document "
                    "already exists"
                )
            },
        )
        self.assertNotIn(
            INTERNAL_OBJECT_KEY,
            response.text,
        )

    def test_service_failure_is_generic(
        self,
    ):
        with patch.object(
            knowledge_api,
            "list_metadata_records",
            side_effect=KnowledgeMetadataError(
                "postgresql://user:password@host/db"
            ),
        ):
            response = client().get(
                "/knowledge"
            )

        self.assertEqual(
            response.status_code,
            503,
        )
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Knowledge metadata "
                    "is unavailable"
                )
            },
        )
        self.assertNotIn(
            "password",
            response.text,
        )

    def test_list_filters_are_forwarded(
        self,
    ):
        ready = record_fixture(
            status="ready",
            page_count=2,
            chunk_count=5,
        )

        with patch.object(
            knowledge_api,
            "list_metadata_records",
            return_value=[ready],
        ) as lister:
            response = client().get(
                "/knowledge",
                params={
                    "limit": 25,
                    "status": "READY",
                    "enabled": "true",
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            len(response.json()),
            1,
        )
        self.assertNotIn(
            "object_key",
            response.json()[0],
        )
        lister.assert_called_once_with(
            limit=25,
            status="ready",
            enabled=True,
        )

    def test_get_and_missing_contract(self):
        with patch.object(
            knowledge_api,
            "get_metadata_record",
            side_effect=[
                record_fixture(),
                None,
            ],
        ):
            found = client().get(
                "/knowledge/knowledge-1"
            )
            missing = client().get(
                "/knowledge/missing"
            )

        self.assertEqual(
            found.status_code,
            200,
        )
        self.assertEqual(
            missing.status_code,
            404,
        )
        self.assertEqual(
            missing.json(),
            {
                "detail": (
                    "Knowledge document "
                    "not found"
                )
            },
        )

    def test_ready_status_contract(self):
        ready = record_fixture(
            status="ready",
            page_count=4,
            chunk_count=8,
        )

        with patch.object(
            knowledge_api,
            "update_metadata_status",
            return_value=ready,
        ) as updater:
            response = client().patch(
                (
                    "/knowledge/"
                    "knowledge-1/status"
                ),
                json={
                    "status": "READY",
                    "page_count": 4,
                    "chunk_count": 8,
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        updater.assert_called_once_with(
            "knowledge-1",
            "ready",
            page_count=4,
            chunk_count=8,
        )

    def test_invalid_status_contract(self):
        with patch.object(
            knowledge_api,
            "update_metadata_status",
        ) as updater:
            response = client().patch(
                (
                    "/knowledge/"
                    "knowledge-1/status"
                ),
                json={
                    "status": "failed",
                    "page_count": 1,
                    "chunk_count": 1,
                },
            )

        self.assertEqual(
            response.status_code,
            400,
        )
        updater.assert_not_called()

    def test_enabled_and_missing_contract(
        self,
    ):
        disabled = record_fixture(
            is_enabled=False
        )

        with patch.object(
            knowledge_api,
            "set_metadata_enabled",
            side_effect=[disabled, None],
        ):
            updated = client().put(
                (
                    "/knowledge/"
                    "knowledge-1/enabled"
                ),
                json={
                    "is_enabled": False
                },
            )
            missing = client().put(
                (
                    "/knowledge/"
                    "missing/enabled"
                ),
                json={
                    "is_enabled": False
                },
            )

        self.assertEqual(
            updated.status_code,
            200,
        )
        self.assertFalse(
            updated.json()["is_enabled"]
        )
        self.assertEqual(
            missing.status_code,
            404,
        )

    def test_delete_is_idempotent(self):
        with patch.object(
            knowledge_api,
            "delete_metadata_record",
            side_effect=[True, False],
        ):
            first = client().delete(
                "/knowledge/knowledge-1"
            )
            second = client().delete(
                "/knowledge/knowledge-1"
            )

        self.assertEqual(
            first.status_code,
            200,
        )
        self.assertTrue(
            first.json()["deleted"]
        )
        self.assertEqual(
            second.status_code,
            200,
        )
        self.assertFalse(
            second.json()["deleted"]
        )

    def test_openapi_contract_is_unique_and_safe(
        self,
    ):
        application_client = client()
        openapi = application_client.get(
            "/openapi.json"
        ).json()
        operation_ids = []

        for path_item in openapi[
            "paths"
        ].values():
            for operation in (
                path_item.values()
            ):
                if not isinstance(
                    operation,
                    dict,
                ):
                    continue

                operation_id = (
                    operation.get(
                        "operationId"
                    )
                )

                if operation_id:
                    operation_ids.append(
                        operation_id
                    )

        self.assertEqual(
            len(operation_ids),
            len(set(operation_ids)),
        )

        response_schema = openapi[
            "components"
        ]["schemas"][
            "KnowledgeDocumentResponse"
        ]["properties"]

        self.assertNotIn(
            "object_key",
            response_schema,
        )
        self.assertNotIn(
            "file_hash",
            response_schema,
        )

    def test_main_registers_knowledge_router(
        self,
    ):
        source = (
            Path("app/main.py")
            .read_text(
                encoding="utf-8-sig"
            )
        )

        self.assertIn(
            "router as knowledge_router",
            source,
        )
        self.assertIn(
            "include_router(knowledge_router)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
