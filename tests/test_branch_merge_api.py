import hashlib
import io
import json
import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config.settings import (
    BranchMergeConfigurationError,
    BranchMergeSettings,
    load_branch_merge_settings,
)
from app.main import create_app
from app.models.chat import BranchMergeResponse
from app.services import (
    branch_merge_security,
    history_service,
)
from app.services.branch_merge_security import (
    BranchMergeRateLimiter,
)
from app.services.branch_merge_service import (
    BranchMergeError,
)


class BranchMergeApiTests(unittest.TestCase):
    PRODUCTION_ORIGIN = "https://onkar-ai.vercel.app"
    LOCAL_ORIGIN = "http://localhost:5173"

    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = str(
            Path(self.temporary_directory.name)
            / "chat_history.db"
        )

        with patch.object(
            history_service,
            "DB_PATH",
            self.database_path,
        ):
            history_service.init_db()

        self.plaintext_token = (
            "test-branch-merge-" + uuid4().hex
        )
        self.token_sha256 = hashlib.sha256(
            self.plaintext_token.encode("utf-8")
        ).hexdigest()
        self.settings = self.make_settings()
        self.executor = Mock(
            side_effect=self.fake_execute
        )
        self.client = self.make_client()

    def tearDown(self):
        self.client.close()
        self.temporary_directory.cleanup()

    def make_settings(
        self,
        *,
        enabled=True,
        origins=None,
        max_body_bytes=1_048_576,
        rate_per_minute=5,
        rate_per_hour=20,
    ):
        return BranchMergeSettings(
            enabled=enabled,
            token_sha256=(
                self.token_sha256 if enabled else ""
            ),
            allowed_origins=tuple(
                origins
                if origins is not None
                else (self.PRODUCTION_ORIGIN,)
            ),
            max_body_bytes=max_body_bytes,
            rate_per_minute=rate_per_minute,
            rate_per_hour=rate_per_hour,
        )

    def make_client(
        self,
        *,
        settings=None,
        executor=None,
        limiter=None,
        database_path=None,
        real_executor=False,
    ):
        app_arguments = {
            "branch_merge_settings": (
                settings or self.settings
            ),
            "branch_merge_db_path": (
                database_path or self.database_path
            ),
            "branch_merge_rate_limiter": limiter,
        }

        if not real_executor:
            app_arguments["branch_merge_executor"] = (
                executor
                if executor is not None
                else self.executor
            )

        app = create_app(
            **app_arguments,
        )
        return TestClient(app)

    def valid_payload(self):
        return {
            "idempotency_key": str(uuid4()),
            "preview_token": "a" * 64,
            "expected": {
                "parent_chat_id": 1,
                "branched_from_message_id": 2,
                "branch_message_id": 3,
                "parent_last_message_id": 4,
                "branch_last_message_id": 5,
            },
            "selected_turns": [
                {
                    "turn_key": "turn:6",
                    "message_ids": [6, 7],
                }
            ],
        }

    def valid_headers(self, **overrides):
        headers = {
            "Origin": self.PRODUCTION_ORIGIN,
            "X-Onkar-Merge-Intent": "v1",
            "Authorization": (
                f"Bearer {self.plaintext_token}"
            ),
        }
        headers.update(overrides)
        return headers

    def post(
        self,
        *,
        client=None,
        payload=None,
        headers=None,
        branch_chat_id=9,
    ):
        return (client or self.client).post(
            f"/chats/{branch_chat_id}/merge-parent",
            json=(
                self.valid_payload()
                if payload is None
                else payload
            ),
            headers=(
                self.valid_headers()
                if headers is None
                else headers
            ),
        )

    def fake_execute(
        self,
        db_path,
        branch_chat_id,
        request,
    ):
        return BranchMergeResponse(
            status="completed",
            replayed=False,
            operation_id=1,
            idempotency_key=request.idempotency_key,
            branch_chat_id=branch_chat_id,
            parent_chat_id=(
                request.expected.parent_chat_id
            ),
            inserted_turn_count=1,
            inserted_message_count=2,
            first_created_parent_message_id=10,
            last_created_parent_message_id=11,
            completed_at="2026-01-01T00:00:00",
            turns=[],
        )

    @staticmethod
    def disabled_settings():
        return BranchMergeSettings(
            enabled=False,
            token_sha256="",
            allowed_origins=(),
            max_body_bytes=1_048_576,
            rate_per_minute=5,
            rate_per_hour=20,
        )

    def enabled_environment(self, **overrides):
        environment = {
            "BRANCH_MERGE_ENABLED": "true",
            "BRANCH_MERGE_TOKEN_SHA256": (
                self.token_sha256
            ),
            "BRANCH_MERGE_ALLOWED_ORIGINS": (
                self.PRODUCTION_ORIGIN
            ),
        }
        environment.update(overrides)
        return environment

    # Configuration

    def test_01_disabled_feature_does_not_register_route(self):
        client = self.make_client(
            settings=self.disabled_settings()
        )

        try:
            response = client.post(
                "/chats/1/merge-parent",
                json=self.valid_payload(),
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 404)

    def test_02_disabled_route_is_absent_from_openapi(self):
        client = self.make_client(
            settings=self.disabled_settings()
        )

        try:
            schema = client.get(
                "/openapi.json"
            ).json()
        finally:
            client.close()

        self.assertNotIn(
            "/chats/{branch_chat_id}/merge-parent",
            schema["paths"],
        )

    def test_03_enabled_without_token_hash_fails_closed(self):
        with self.assertRaises(
            BranchMergeConfigurationError
        ):
            load_branch_merge_settings(
                self.enabled_environment(
                    BRANCH_MERGE_TOKEN_SHA256=""
                )
            )

    def test_04_enabled_with_malformed_hash_fails_closed(self):
        for malformed in (
            "abc",
            "A" * 64,
            "g" * 64,
            "a" * 63,
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaises(
                    BranchMergeConfigurationError
                ):
                    load_branch_merge_settings(
                        self.enabled_environment(
                            BRANCH_MERGE_TOKEN_SHA256=(
                                malformed
                            )
                        )
                    )

    def test_05_enabled_without_origins_fails_closed(self):
        with self.assertRaises(
            BranchMergeConfigurationError
        ):
            load_branch_merge_settings(
                self.enabled_environment(
                    BRANCH_MERGE_ALLOWED_ORIGINS=""
                )
            )

    def test_06_wildcard_origin_is_rejected(self):
        with self.assertRaises(
            BranchMergeConfigurationError
        ):
            load_branch_merge_settings(
                self.enabled_environment(
                    BRANCH_MERGE_ALLOWED_ORIGINS="*"
                )
            )

    def test_07_valid_configuration_registers_route(self):
        schema = self.client.get(
            "/openapi.json"
        ).json()
        self.assertIn(
            "/chats/{branch_chat_id}/merge-parent",
            schema["paths"],
        )

    # Authentication

    def test_08_missing_token_returns_401(self):
        headers = self.valid_headers()
        headers.pop("Authorization")
        response = self.post(headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers["www-authenticate"],
            "Bearer",
        )

    def test_09_incorrect_token_has_identical_401_body(self):
        missing_headers = self.valid_headers()
        missing_headers.pop("Authorization")
        missing = self.post(
            headers=missing_headers
        )
        incorrect = self.post(
            headers=self.valid_headers(
                Authorization="Bearer definitely-wrong"
            )
        )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(incorrect.status_code, 401)
        self.assertEqual(missing.json(), incorrect.json())

    def test_10_malformed_bearer_has_identical_401_body(self):
        missing_headers = self.valid_headers()
        missing_headers.pop("Authorization")
        missing = self.post(
            headers=missing_headers
        )
        malformed = self.post(
            headers=self.valid_headers(
                Authorization="Basic not-a-bearer"
            )
        )
        self.assertEqual(malformed.status_code, 401)
        self.assertEqual(missing.json(), malformed.json())

    def test_11_valid_token_passes_authentication(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.executor.assert_called_once()

    def test_12_token_and_hash_never_appear_in_response(self):
        response = self.post(
            headers=self.valid_headers(
                Authorization="Bearer wrong-token"
            )
        )
        response_text = response.text
        self.assertNotIn(
            self.plaintext_token,
            response_text,
        )
        self.assertNotIn(
            self.token_sha256,
            response_text,
        )

    def test_13_token_and_hash_never_appear_in_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        api_logger = logging.getLogger(
            "app.api.branch_merge"
        )
        api_logger.addHandler(handler)

        try:
            self.post(
                headers=self.valid_headers(
                    Authorization=(
                        f"Bearer {self.plaintext_token}-bad"
                    )
                )
            )
        finally:
            api_logger.removeHandler(handler)

        output = stream.getvalue()
        self.assertNotIn(self.plaintext_token, output)
        self.assertNotIn(self.token_sha256, output)

    # Origin and intent

    def test_14_missing_origin_is_rejected(self):
        headers = self.valid_headers()
        headers.pop("Origin")
        response = self.post(headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_15_null_origin_is_rejected(self):
        response = self.post(
            headers=self.valid_headers(Origin="null")
        )
        self.assertEqual(response.status_code, 403)

    def test_16_evil_origin_is_rejected(self):
        response = self.post(
            headers=self.valid_headers(
                Origin="https://evil.example"
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_17_suffix_lookalike_origin_is_rejected(self):
        response = self.post(
            headers=self.valid_headers(
                Origin=(
                    "https://onkar-ai.vercel.app.evil.example"
                )
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_18_wrong_port_is_rejected(self):
        settings = self.make_settings(
            origins=(self.LOCAL_ORIGIN,)
        )
        client = self.make_client(settings=settings)

        try:
            response = self.post(
                client=client,
                headers=self.valid_headers(
                    Origin="http://localhost:5174"
                ),
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 403)

    def test_19_exact_production_origin_is_accepted(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)

    def test_20_exact_localhost_origin_is_accepted(self):
        settings = self.make_settings(
            origins=(self.LOCAL_ORIGIN,)
        )
        client = self.make_client(settings=settings)

        try:
            response = self.post(
                client=client,
                headers=self.valid_headers(
                    Origin=self.LOCAL_ORIGIN
                ),
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)

    def test_21_spoofed_allowed_origin_without_token_is_rejected(self):
        headers = self.valid_headers()
        headers.pop("Authorization")
        response = self.post(headers=headers)
        self.assertEqual(response.status_code, 401)

    def test_22_missing_intent_header_is_rejected(self):
        headers = self.valid_headers()
        headers.pop("X-Onkar-Merge-Intent")
        response = self.post(headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_23_wrong_intent_header_is_rejected(self):
        response = self.post(
            headers=self.valid_headers(
                **{"X-Onkar-Merge-Intent": "v2"}
            )
        )
        self.assertEqual(response.status_code, 403)

    # Content and size

    def test_24_wrong_content_type_returns_415(self):
        response = self.client.post(
            "/chats/9/merge-parent",
            content="not-json",
            headers={
                **self.valid_headers(),
                "Content-Type": "text/plain",
            },
        )
        self.assertEqual(response.status_code, 415)

    def test_25_invalid_json_returns_safe_400(self):
        response = self.client.post(
            "/chats/9/merge-parent",
            content=b"{not valid json",
            headers={
                **self.valid_headers(),
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("not valid json", response.text)

    def test_26_pydantic_error_is_sanitized(self):
        payload = self.valid_payload()
        payload["expected"]["parent_chat_id"] = "secret-value"
        response = self.post(payload=payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("secret-value", response.text)
        error = response.json()["detail"]["errors"][0]
        self.assertEqual(
            set(error),
            {"loc", "type", "msg"},
        )

    def test_27_role_content_and_timestamp_fields_are_rejected(self):
        for field in ("role", "content", "timestamp"):
            payload = self.valid_payload()
            payload[field] = "must-not-be-accepted"
            response = self.post(payload=payload)

            with self.subTest(field=field):
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "INVALID_MERGE_REQUEST",
                )

    def test_28_oversized_content_length_returns_413_first(self):
        settings = self.make_settings(max_body_bytes=16)
        executor = Mock(side_effect=self.fake_execute)
        client = self.make_client(
            settings=settings,
            executor=executor,
        )

        try:
            response = client.post(
                "/chats/9/merge-parent",
                content=b"{}",
                headers={
                    **self.valid_headers(),
                    "Content-Type": "application/json",
                    "Content-Length": "17",
                },
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 413)
        executor.assert_not_called()

    def test_29_oversized_streamed_body_returns_413(self):
        settings = self.make_settings(max_body_bytes=32)
        executor = Mock(side_effect=self.fake_execute)
        client = self.make_client(
            settings=settings,
            executor=executor,
        )

        def body_chunks():
            yield b"{" + b"x" * 20
            yield b"y" * 20 + b"}"

        try:
            response = client.post(
                "/chats/9/merge-parent",
                content=body_chunks(),
                headers={
                    **self.valid_headers(),
                    "Content-Type": "application/json",
                },
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 413)
        executor.assert_not_called()

    def test_30_empty_body_is_rejected_safely(self):
        response = self.client.post(
            "/chats/9/merge-parent",
            content=b"",
            headers={
                **self.valid_headers(),
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "INVALID_JSON",
        )

    # Rate limiting

    def test_31_failed_auth_burst_returns_429(self):
        limiter = BranchMergeRateLimiter(
            10,
            20,
            failed_rate_per_minute=2,
            failed_rate_per_hour=20,
        )
        client = self.make_client(limiter=limiter)
        headers = self.valid_headers(
            Authorization="Bearer wrong"
        )

        try:
            self.post(client=client, headers=headers)
            self.post(client=client, headers=headers)
            response = self.post(
                client=client,
                headers=headers,
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 429)

    def test_32_authenticated_minute_limit_returns_429(self):
        limiter = BranchMergeRateLimiter(1, 20)
        client = self.make_client(limiter=limiter)

        try:
            self.post(client=client)
            response = self.post(client=client)
        finally:
            client.close()

        self.assertEqual(response.status_code, 429)

    def test_33_authenticated_hour_limit_returns_429(self):
        now = [1000.0]
        limiter = BranchMergeRateLimiter(
            5,
            1,
            clock=lambda: now[0],
        )
        client = self.make_client(limiter=limiter)

        try:
            self.post(client=client)
            now[0] += 61
            response = self.post(client=client)
        finally:
            client.close()

        self.assertEqual(response.status_code, 429)

    def test_34_rate_limit_response_has_retry_after(self):
        limiter = BranchMergeRateLimiter(1, 20)
        client = self.make_client(limiter=limiter)

        try:
            self.post(client=client)
            response = self.post(client=client)
        finally:
            client.close()

        self.assertGreaterEqual(
            int(response.headers["retry-after"]),
            1,
        )

    def test_35_rate_limited_request_does_not_execute_service(self):
        executor = Mock(side_effect=self.fake_execute)
        limiter = BranchMergeRateLimiter(1, 20)
        client = self.make_client(
            executor=executor,
            limiter=limiter,
        )

        try:
            self.post(client=client)
            self.post(client=client)
        finally:
            client.close()

        self.assertEqual(executor.call_count, 1)

    # Service mapping

    def test_36_every_service_error_maps_to_expected_status(self):
        expected_statuses = {
            "BRANCH_NOT_FOUND": 404,
            "PARENT_MISSING": 409,
            "DETACHED_BRANCH": 409,
            "INVALID_BRANCH_BOUNDARY": 409,
            "STALE_PREVIEW": 409,
            "IDEMPOTENCY_KEY_REUSED": 409,
            "MERGE_ALREADY_COMPLETED": 409,
            "EMPTY_SELECTION": 422,
            "INVALID_SELECTED_TURN": 422,
            "ORPHAN_SELECTED_MESSAGE": 422,
            "DUPLICATE_SELECTED_ID": 422,
            "MESSAGE_NOT_OWNED_BY_BRANCH": 422,
            "MESSAGE_OUTSIDE_BRANCH_CONTINUATION": 422,
            "MERGE_BUSY": 503,
            "MERGE_FAILED": 500,
        }

        for code, expected_status in expected_statuses.items():
            error = BranchMergeError(
                code,
                "Safe service message.",
                http_status=418,
                retryable=(code == "MERGE_BUSY"),
            )
            executor = Mock(side_effect=error)
            client = self.make_client(
                executor=executor
            )

            try:
                response = self.post(client=client)
            finally:
                client.close()

            with self.subTest(code=code):
                self.assertEqual(
                    response.status_code,
                    expected_status,
                )

    def test_37_merge_busy_returns_503_and_retry_after(self):
        executor = Mock(
            side_effect=BranchMergeError(
                "MERGE_BUSY",
                "Database busy.",
                http_status=503,
                retryable=True,
            )
        )
        client = self.make_client(executor=executor)

        try:
            response = self.post(client=client)
        finally:
            client.close()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "1")
        self.assertTrue(response.json()["detail"]["retryable"])

    def test_38_unexpected_exception_returns_generic_500(self):
        executor = Mock(
            side_effect=RuntimeError(
                "sqlite path C:/secret/database.db"
            )
        )
        client = self.make_client(executor=executor)

        try:
            response = self.post(client=client)
        finally:
            client.close()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"]["message"],
            "The branch merge could not be completed.",
        )

    def test_39_internal_error_details_do_not_leak(self):
        secret_detail = "SELECT * FROM secret C:/private.db"
        executor = Mock(
            side_effect=RuntimeError(secret_detail)
        )
        client = self.make_client(executor=executor)

        try:
            response = self.post(client=client)
        finally:
            client.close()

        self.assertNotIn(secret_detail, response.text)

    # Successful disposable execution

    def seed_real_merge(self):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO chats (title, created_at)
                VALUES ('Parent', '2026-01-01T09:00:00')
                """
            )
            parent_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, role, content, created_at
                )
                VALUES (?, 'user', 'Shared prompt', ?)
                """,
                (parent_id, "2026-01-01T09:00:00"),
            )
            parent_source_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, role, content, created_at
                )
                VALUES (?, 'assistant', 'Parent answer', ?)
                """,
                (parent_id, "2026-01-01T09:01:00"),
            )
            cursor.execute(
                """
                INSERT INTO chats (
                    title,
                    created_at,
                    parent_chat_id,
                    branched_from_message_id
                )
                VALUES ('Branch', ?, ?, ?)
                """,
                (
                    "2026-01-01T09:02:00",
                    parent_id,
                    parent_source_id,
                ),
            )
            branch_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, role, content, created_at
                )
                VALUES (?, 'user', 'Shared prompt', ?)
                """,
                (branch_id, "2026-01-01T09:00:00"),
            )
            branch_source_id = cursor.lastrowid
            cursor.execute(
                """
                UPDATE chats
                SET branch_message_id = ?
                WHERE id = ?
                """,
                (branch_source_id, branch_id),
            )
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, role, content, created_at
                )
                VALUES (?, 'user', 'Branch prompt', ?)
                """,
                (branch_id, "2026-01-01T09:03:00"),
            )
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, role, content, created_at
                )
                VALUES (?, 'assistant', 'Branch answer', ?)
                """,
                (branch_id, "2026-01-01T09:04:00"),
            )
            connection.commit()
        finally:
            connection.close()

        with patch.object(
            history_service,
            "DB_PATH",
            self.database_path,
        ):
            comparison = (
                history_service
                .compare_chat_with_parent(branch_id)
            )

        preview = comparison["merge_preview"]
        selected_turns = [
            {
                "turn_key": turn["turn_key"],
                "message_ids": list(
                    turn["message_ids"]
                ),
            }
            for turn in preview["turns"]
            if turn["selectable"]
        ]
        payload = {
            "idempotency_key": str(uuid4()),
            "preview_token": preview["preview_token"],
            "expected": {
                "parent_chat_id": parent_id,
                "branched_from_message_id": (
                    parent_source_id
                ),
                "branch_message_id": branch_source_id,
                "parent_last_message_id": preview[
                    "expected_parent_last_message_id"
                ],
                "branch_last_message_id": preview[
                    "expected_branch_last_message_id"
                ],
            },
            "selected_turns": selected_turns,
        }
        return parent_id, branch_id, payload

    def run_real_merge(self, *, replay=False):
        parent_id, branch_id, payload = (
            self.seed_real_merge()
        )
        client = self.make_client(
            database_path=self.database_path,
            real_executor=True,
        )

        try:
            first = self.post(
                client=client,
                payload=payload,
                branch_chat_id=branch_id,
            )
            second = None

            if replay:
                second = self.post(
                    client=client,
                    payload=payload,
                    branch_chat_id=branch_id,
                )
        finally:
            client.close()

        return parent_id, branch_id, payload, first, second

    def database_value(self, sql, parameters=()):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            return connection.execute(
                sql,
                parameters,
            ).fetchone()[0]
        finally:
            connection.close()

    def test_40_valid_secure_request_executes_disposable_merge(self):
        _, _, _, response, _ = self.run_real_merge()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["inserted_message_count"],
            2,
        )

    def test_41_same_request_replays_as_completed(self):
        _, _, _, first, replay = self.run_real_merge(
            replay=True
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])

    def test_42_replay_does_not_duplicate_parent_messages(self):
        parent_id, _, _, _, _ = self.run_real_merge(
            replay=True
        )
        count = self.database_value(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            (parent_id,),
        )
        self.assertEqual(count, 4)

    def test_43_source_branch_remains_unchanged(self):
        _, branch_id, _, _, _ = self.run_real_merge()
        count = self.database_value(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            (branch_id,),
        )
        self.assertEqual(count, 3)

    def test_44_success_has_all_no_store_security_headers(self):
        response = self.post()
        expected = {
            "cache-control": "no-store",
            "pragma": "no-cache",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "x-frame-options": "DENY",
        }

        for name, value in expected.items():
            with self.subTest(header=name):
                self.assertEqual(
                    response.headers[name],
                    value,
                )

        self.assertIn(
            "default-src 'none'",
            response.headers[
                "content-security-policy"
            ],
        )

    def test_45_audit_rows_and_mappings_are_persisted(self):
        _, _, _, _, _ = self.run_real_merge()
        operation_count = self.database_value(
            "SELECT COUNT(*) FROM branch_merge_operations"
        )
        mapping_count = self.database_value(
            "SELECT COUNT(*) FROM branch_merge_message_mappings"
        )
        self.assertEqual(operation_count, 1)
        self.assertEqual(mapping_count, 2)

    # Additional security assertions

    def test_46_missing_and_wrong_auth_both_hash_once(self):
        real_helper = (
            branch_merge_security
            ._hash_submitted_token
        )

        with patch.object(
            branch_merge_security,
            "_hash_submitted_token",
            wraps=real_helper,
        ) as hash_helper:
            missing_headers = self.valid_headers()
            missing_headers.pop("Authorization")
            self.post(headers=missing_headers)
            self.post(
                headers=self.valid_headers(
                    Authorization="Bearer wrong"
                )
            )

        self.assertEqual(hash_helper.call_count, 2)

    def test_47_request_body_content_is_not_logged(self):
        unique_content = "private-body-" + uuid4().hex
        executor = Mock(
            side_effect=RuntimeError("private failure")
        )
        client = self.make_client(executor=executor)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        api_logger = logging.getLogger(
            "app.api.branch_merge"
        )
        api_logger.addHandler(handler)
        payload = self.valid_payload()
        payload["content"] = unique_content

        try:
            self.post(client=client, payload=payload)
        finally:
            api_logger.removeHandler(handler)
            client.close()

        self.assertNotIn(unique_content, stream.getvalue())

    def test_48_validation_never_echoes_raw_values(self):
        secret_value = "private-content-" + uuid4().hex
        payload = self.valid_payload()
        payload["content"] = secret_value
        response = self.post(payload=payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret_value, response.text)
        self.assertNotIn(self.plaintext_token, response.text)
        self.assertNotIn(self.token_sha256, response.text)

    def test_49_route_uses_configured_disposable_db_path(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        called_path = self.executor.call_args.args[0]
        self.assertEqual(called_path, self.database_path)

    def test_50_existing_public_get_routes_remain_registered(self):
        schema = self.client.get(
            "/openapi.json"
        ).json()
        self.assertIn("get", schema["paths"]["/"])
        self.assertIn("get", schema["paths"]["/chats"])
        self.assertIn(
            "get",
            schema["paths"][
                "/chats/{chat_id}/messages"
            ],
        )

    def test_51_application_json_charset_is_accepted(self):
        response = self.client.post(
            "/chats/9/merge-parent",
            content=json.dumps(
                self.valid_payload()
            ).encode("utf-8"),
            headers={
                **self.valid_headers(),
                "Content-Type": (
                    "application/json; charset=utf-8"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_52_origin_configuration_normalizes_one_safe_slash(self):
        settings = load_branch_merge_settings(
            self.enabled_environment(
                BRANCH_MERGE_ALLOWED_ORIGINS=(
                    f"{self.PRODUCTION_ORIGIN}/"
                )
            )
        )
        self.assertEqual(
            settings.allowed_origins,
            (self.PRODUCTION_ORIGIN,),
        )


if __name__ == "__main__":
    unittest.main()
