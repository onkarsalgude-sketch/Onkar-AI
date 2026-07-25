import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.memory as memory_api
from app.memory.memory import MemoryPersistenceError


TOKEN = "memory-test-token"
TOKEN_DIGEST = hashlib.sha256(
    TOKEN.encode("utf-8")
).hexdigest()

AUTH_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
}


def client() -> TestClient:
    application = FastAPI()
    application.include_router(
        memory_api.router
    )
    return TestClient(application)


class MemoryApiTests(
    unittest.TestCase
):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "MEMORY_API_TOKEN_SHA256":
                    TOKEN_DIGEST,
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(
            self.environment.stop
        )

    def test_get_memory_requires_bearer_token(
        self,
    ):
        with patch.object(
            memory_api,
            "get",
        ) as memory_get:
            response = client().get(
                "/memory"
            )

        self.assertEqual(
            response.status_code,
            401,
        )

        self.assertEqual(
            response.json(),
            {
                "detail":
                    "Memory authorization failed.",
            },
        )

        memory_get.assert_not_called()

    def test_get_memory_rejects_wrong_bearer_without_leaking_token(
        self,
    ):
        response = client().get(
            "/memory",
            headers={
                "Authorization":
                    "Bearer definitely-wrong",
            },
        )

        self.assertEqual(
            response.status_code,
            401,
        )

        self.assertNotIn(
            "definitely-wrong",
            str(response.json()),
        )

    def test_get_memory_returns_bounded_preview_contract(
        self,
    ):
        with patch.object(
            memory_api,
            "get",
            return_value=[
                {
                    "role": "user",
                    "content": "Remember this.",
                },
                {
                    "role": "assistant",
                    "content": "Stored response.",
                },
            ],
        ) as memory_get:
            response = client().get(
                "/memory",
                params={
                    "limit": 2,
                },
                headers=AUTH_HEADERS,
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json(),
            {
                "service": "memory",
                "items": [
                    {
                        "role": "user",
                        "preview": "Remember this.",
                        "truncated": False,
                    },
                    {
                        "role": "assistant",
                        "preview": "Stored response.",
                        "truncated": False,
                    },
                ],
                "returned": 2,
                "limit": 2,
            },
        )

        memory_get.assert_called_once_with(
            limit=2
        )

    def test_get_memory_default_and_bounds_are_safe(
        self,
    ):
        with patch.object(
            memory_api,
            "get",
            return_value=[],
        ) as memory_get:
            default_response = client().get(
                "/memory",
                headers=AUTH_HEADERS,
            )

        self.assertEqual(
            default_response.status_code,
            200,
        )

        self.assertEqual(
            default_response.json()["limit"],
            6,
        )

        memory_get.assert_called_once_with(
            limit=6
        )

        for invalid_limit in (
            0,
            21,
        ):
            with self.subTest(
                limit=invalid_limit
            ):
                response = client().get(
                    "/memory",
                    params={
                        "limit":
                            invalid_limit,
                    },
                    headers=AUTH_HEADERS,
                )

                self.assertEqual(
                    response.status_code,
                    422,
                )

    def test_get_memory_truncates_preview_without_inventing_content(
        self,
    ):
        source = "x" * 300

        with patch.object(
            memory_api,
            "get",
            return_value=[
                {
                    "role": "user",
                    "content": source,
                },
            ],
        ):
            response = client().get(
                "/memory",
                headers=AUTH_HEADERS,
            )

        item = response.json()[
            "items"
        ][0]

        self.assertEqual(
            item["preview"],
            source[:240],
        )

        self.assertTrue(
            item["truncated"]
        )

    def test_get_memory_failure_is_generic(
        self,
    ):
        with patch.object(
            memory_api,
            "get",
            side_effect=(
                MemoryPersistenceError()
            ),
        ):
            response = client().get(
                "/memory",
                headers=AUTH_HEADERS,
            )

        self.assertEqual(
            response.status_code,
            503,
        )

        self.assertEqual(
            response.json(),
            {
                "detail":
                    "Memory is unavailable.",
            },
        )

    def test_missing_or_malformed_server_digest_fails_closed(
        self,
    ):
        for configured in (
            "",
            "not-a-sha256",
        ):
            with self.subTest(
                digest=configured
            ):
                with patch.dict(
                    os.environ,
                    {
                        "MEMORY_API_TOKEN_SHA256":
                            configured,
                    },
                    clear=False,
                ):
                    with patch.object(
                        memory_api,
                        "get",
                    ) as memory_get:
                        response = client().get(
                            "/memory",
                            headers=AUTH_HEADERS,
                        )

                    self.assertEqual(
                        response.status_code,
                        503,
                    )

                    memory_get.assert_not_called()

    def test_delete_memory_reuses_existing_clear_operation(
        self,
    ):
        with patch.object(
            memory_api,
            "clear",
        ) as memory_clear:
            response = client().delete(
                "/memory",
                headers=AUTH_HEADERS,
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json(),
            {
                "service": "memory",
                "cleared": True,
                "message": "Memory cleared.",
            },
        )

        memory_clear.assert_called_once_with()

    def test_delete_memory_failure_is_generic(
        self,
    ):
        with patch.object(
            memory_api,
            "clear",
            side_effect=RuntimeError(
                "postgresql://user:secret@host/db"
            ),
        ):
            response = client().delete(
                "/memory",
                headers=AUTH_HEADERS,
            )

        self.assertEqual(
            response.status_code,
            503,
        )

        body = str(
            response.json()
        )

        self.assertNotIn(
            "secret",
            body,
        )

    def test_openapi_and_main_registration_are_bounded(
        self,
    ):
        schema = client().get(
            "/openapi.json"
        ).json()

        operations = schema[
            "paths"
        ][
            "/memory"
        ]

        self.assertEqual(
            set(operations),
            {
                "get",
                "delete",
            },
        )

        self.assertNotIn(
            "post",
            operations,
        )

        source = (
            Path("app/main.py")
            .read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            source.count(
                "router as memory_router"
            ),
            1,
        )

        self.assertEqual(
            source.count(
                "include_router(memory_router)"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
