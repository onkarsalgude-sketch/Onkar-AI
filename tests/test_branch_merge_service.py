import copy
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from concurrent.futures import (
    ThreadPoolExecutor,
)
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.models.chat import (
    BranchMergeRequest,
    BranchMergeResponse,
    ChatCompareParentResponse,
)
from app.services import (
    branch_merge_service,
    history_service,
)
from app.services.branch_merge_service import (
    BRANCH_MERGE_PREVIEW_VERSION,
    BranchMergeError,
    _build_branch_merge_preview_token,
    _build_branch_merge_request_fingerprint,
    _build_canonical_branch_turns,
    _canonical_sha256,
    _is_positive_integer,
    execute_branch_merge,
)
from pydantic import ValidationError


class DisposableDatabaseTestCase(
    unittest.TestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = str(
            Path(
                self.temporary_directory.name
            )
            / "chat_history.db"
        )
        self.database_patch = patch.object(
            history_service,
            "DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        history_service.init_db()

    def tearDown(self):
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(
            self.database_path
        )

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def insert_chat(
        self,
        title,
        *,
        parent_chat_id=None,
        branched_from_message_id=None,
        branch_message_id=None,
    ):
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chats (
                    title,
                    created_at,
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    title,
                    "2026-01-01T00:00:00",
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id,
                ),
            )
            return cursor.lastrowid

    def insert_message(
        self,
        chat_id,
        role,
        content,
        *,
        created_at="2026-01-01T00:00:00",
        sources_json="[]",
        attachment_json=None,
    ):
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    attachment_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    role,
                    content,
                    created_at,
                    sources_json,
                    attachment_json,
                ),
            )
            return cursor.lastrowid

    def insert_operation(
        self,
        key,
        branch_chat_id,
        parent_chat_id,
    ):
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO branch_merge_operations (
                    idempotency_key,
                    request_fingerprint,
                    preview_token,
                    branch_chat_id,
                    parent_chat_id,
                    branched_from_message_id,
                    branch_message_id,
                    expected_parent_last_message_id,
                    expected_branch_last_message_id,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    "request-fingerprint",
                    "preview-token",
                    branch_chat_id,
                    parent_chat_id,
                    1,
                    2,
                    3,
                    4,
                    "completed",
                    "2026-01-01T00:00:00",
                ),
            )
            return cursor.lastrowid


class BranchMergeSchemaTests(
    DisposableDatabaseTestCase
):
    def test_fresh_init_creates_merge_tables(self):
        with self.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

        self.assertIn(
            "branch_merge_operations",
            tables,
        )
        self.assertIn(
            "branch_merge_message_mappings",
            tables,
        )

    def test_repeated_init_is_idempotent(self):
        history_service.init_db()
        history_service.init_db()

        with self.connect() as connection:
            table_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name LIKE 'branch_merge_%'
                """
            ).fetchone()[0]

        self.assertEqual(table_count, 2)

    def test_required_indexes_exist(self):
        expected_indexes = {
            "idx_branch_merge_operations_branch",
            "idx_branch_merge_operations_parent",
            "idx_branch_merge_mappings_operation",
            "idx_branch_merge_mappings_chats",
        }

        with self.connect() as connection:
            actual_indexes = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index'
                    """
                )
            }

        self.assertTrue(
            expected_indexes.issubset(
                actual_indexes
            )
        )

    def test_unique_idempotency_key_constraint(self):
        parent_id = self.insert_chat("Parent")
        branch_id = self.insert_chat(
            "Branch",
            parent_chat_id=parent_id,
        )
        self.insert_operation(
            "same-key",
            branch_id,
            parent_id,
        )

        with self.assertRaises(
            sqlite3.IntegrityError
        ):
            self.insert_operation(
                "same-key",
                branch_id,
                parent_id,
            )

    def test_unique_source_mapping_across_operations(self):
        parent_id = self.insert_chat("Parent")
        branch_id = self.insert_chat(
            "Branch",
            parent_chat_id=parent_id,
        )
        first_operation = self.insert_operation(
            "operation-one",
            branch_id,
            parent_id,
        )
        second_operation = self.insert_operation(
            "operation-two",
            branch_id,
            parent_id,
        )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO folders (name, created_at)
                VALUES (?, ?)
                """,
                (
                    "Unrelated folder",
                    "2026-01-01T00:00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO branch_merge_message_mappings (
                    merge_operation_id,
                    branch_chat_id,
                    parent_chat_id,
                    turn_key,
                    turn_position,
                    message_position,
                    source_branch_message_id,
                    created_parent_message_id,
                    created_message_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    first_operation,
                    branch_id,
                    parent_id,
                    "user:10",
                    0,
                    0,
                    10,
                    20,
                    "fingerprint-one",
                ),
            )

        with self.assertRaises(
            sqlite3.IntegrityError
        ):
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO branch_merge_message_mappings (
                        merge_operation_id,
                        branch_chat_id,
                        parent_chat_id,
                        turn_key,
                        turn_position,
                        message_position,
                        source_branch_message_id,
                        created_parent_message_id,
                        created_message_fingerprint
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        second_operation,
                        branch_id,
                        parent_id,
                        "user:10",
                        0,
                        0,
                        10,
                        21,
                        "fingerprint-two",
                    ),
                )

    def test_audit_rows_survive_chat_deletion(self):
        parent_id = self.insert_chat("Parent")
        branch_id = self.insert_chat(
            "Branch",
            parent_chat_id=parent_id,
        )
        operation_id = self.insert_operation(
            "durable-audit",
            branch_id,
            parent_id,
        )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO branch_merge_message_mappings (
                    merge_operation_id,
                    branch_chat_id,
                    parent_chat_id,
                    turn_key,
                    turn_position,
                    message_position,
                    source_branch_message_id,
                    created_parent_message_id,
                    created_message_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    branch_id,
                    parent_id,
                    "user:10",
                    0,
                    0,
                    10,
                    20,
                    "fingerprint",
                ),
            )

        history_service.delete_chat(branch_id)

        with self.connect() as connection:
            operation_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM branch_merge_operations
                    """
                ).fetchone()[0]
            )
            mapping_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM branch_merge_message_mappings
                """
            ).fetchone()[0]

        self.assertEqual(operation_count, 1)
        self.assertEqual(mapping_count, 1)


class CanonicalTurnTests(unittest.TestCase):
    source = {
        "id": 100,
        "role": "user",
    }

    def build(self, messages, merged=()):
        return _build_canonical_branch_turns(
            100,
            self.source,
            messages,
            merged,
        )

    def test_positive_integer_validation(self):
        self.assertTrue(_is_positive_integer(1))
        self.assertFalse(_is_positive_integer(True))
        self.assertFalse(_is_positive_integer(0))
        self.assertFalse(_is_positive_integer(-1))
        self.assertFalse(_is_positive_integer("1"))

    def test_normal_user_assistant_turn(self):
        units = self.build(
            [
                {"id": 101, "role": "user"},
                {
                    "id": 102,
                    "role": "assistant",
                },
            ]
        )

        self.assertEqual(
            units,
            [
                {
                    "turn_key": "user:101",
                    "type": "turn",
                    "selectable": True,
                    "anchor_message_id": 101,
                    "message_ids": [101, 102],
                    "reason": None,
                }
            ],
        )

    def test_multiple_turns_preserve_id_order(self):
        units = self.build(
            [
                {"id": 104, "role": "assistant"},
                {"id": 103, "role": "user"},
                {"id": 102, "role": "assistant"},
                {"id": 101, "role": "user"},
            ]
        )

        self.assertEqual(
            [unit["message_ids"] for unit in units],
            [[101, 102], [103, 104]],
        )

    def test_source_continuation_excludes_source(self):
        units = self.build(
            [
                {
                    "id": 101,
                    "role": "assistant",
                },
                {"id": 102, "role": "system"},
            ]
        )

        self.assertEqual(
            units[0]["turn_key"],
            "source:100",
        )
        self.assertEqual(
            units[0]["anchor_message_id"],
            100,
        )
        self.assertEqual(
            units[0]["message_ids"],
            [101, 102],
        )
        self.assertNotIn(
            100,
            units[0]["message_ids"],
        )

    def test_unanchored_assistant_system_is_locked(self):
        units = _build_canonical_branch_turns(
            100,
            {"id": 100, "role": "assistant"},
            [
                {
                    "id": 101,
                    "role": "assistant",
                },
                {"id": 102, "role": "system"},
            ],
            (),
        )

        self.assertEqual(units[0]["type"], "locked")
        self.assertFalse(units[0]["selectable"])
        self.assertEqual(
            units[0]["reason"],
            "orphan_messages",
        )

    def test_unknown_role_is_locked(self):
        units = self.build(
            [{"id": 101, "role": "tool"}]
        )

        self.assertEqual(
            units[0]["reason"],
            "unknown_role",
        )
        self.assertEqual(
            units[0]["message_ids"],
            [101],
        )

    def test_invalid_id_is_locked_without_identity(self):
        units = self.build(
            [{"id": "101", "role": "user"}]
        )

        self.assertEqual(
            units[0]["reason"],
            "invalid_message_id",
        )
        self.assertEqual(units[0]["message_ids"], [])

    def test_duplicate_id_is_locked_without_identity(self):
        units = self.build(
            [
                {"id": 101, "role": "user"},
                {
                    "id": 101,
                    "role": "assistant",
                },
            ]
        )

        self.assertEqual(
            units[0]["reason"],
            "duplicate_message_id",
        )
        self.assertEqual(units[0]["message_ids"], [])

    def test_already_merged_id_locks_whole_unit(self):
        units = self.build(
            [
                {"id": 101, "role": "user"},
                {
                    "id": 102,
                    "role": "assistant",
                },
            ],
            merged={102},
        )

        self.assertFalse(units[0]["selectable"])
        self.assertEqual(
            units[0]["reason"],
            "already_merged",
        )
        self.assertEqual(
            units[0]["message_ids"],
            [101, 102],
        )

    def test_trailing_user_only_is_incomplete(self):
        units = self.build(
            [{"id": 101, "role": "user"}]
        )

        self.assertFalse(units[0]["selectable"])
        self.assertEqual(
            units[0]["reason"],
            "incomplete_turn",
        )

    def test_duplicate_content_remains_id_based(self):
        units = self.build(
            [
                {
                    "id": 101,
                    "role": "user",
                    "content": "same",
                },
                {
                    "id": 102,
                    "role": "assistant",
                    "content": "same",
                },
                {
                    "id": 103,
                    "role": "user",
                    "content": "same",
                },
                {
                    "id": 104,
                    "role": "assistant",
                    "content": "same",
                },
            ]
        )

        self.assertEqual(
            [unit["turn_key"] for unit in units],
            ["user:101", "user:103"],
        )


class PreviewTokenTests(unittest.TestCase):
    def setUp(self):
        self.arguments = {
            "version": BRANCH_MERGE_PREVIEW_VERSION,
            "branch_chat_id": 2,
            "branch_chat_title": "Branch",
            "parent_chat_id": 1,
            "parent_chat_title": "Parent",
            "branched_from_message_id": 10,
            "branch_message_id": 20,
            "parent_source_message": self.record(
                10,
                "user",
                "source",
            ),
            "branch_source_message": self.record(
                20,
                "user",
                "source",
            ),
            "parent_only_messages": [
                self.record(
                    11,
                    "assistant",
                    "parent",
                )
            ],
            "branch_only_messages": [
                self.record(
                    21,
                    "assistant",
                    "branch",
                )
            ],
            "expected_parent_last_message_id": 11,
            "expected_branch_last_message_id": 21,
            "already_merged_source_message_ids": [],
            "turns": [
                {
                    "turn_key": "source:20",
                    "type": "source",
                    "selectable": True,
                    "anchor_message_id": 20,
                    "message_ids": [21],
                    "reason": None,
                }
            ],
        }

    @staticmethod
    def record(
        message_id,
        role,
        content,
        *,
        attachment=False,
        sources=False,
    ):
        return {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": "2026-01-01T00:00:00",
            "has_attachment_metadata": attachment,
            "has_source_metadata": sources,
        }

    def token(self, arguments=None):
        return _build_branch_merge_preview_token(
            **(arguments or self.arguments)
        )

    def changed(self, mutate):
        arguments = copy.deepcopy(
            self.arguments
        )
        mutate(arguments)
        self.assertNotEqual(
            self.token(),
            self.token(arguments),
        )

    def test_token_is_deterministic_sha256(self):
        first = self.token()
        second = self.token(
            copy.deepcopy(self.arguments)
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(first, first.lower())
        self.assertTrue(
            all(
                character in "0123456789abcdef"
                for character in first
            )
        )

    def test_parent_content_changes_token(self):
        self.changed(
            lambda value: value[
                "parent_only_messages"
            ][0].update(content="changed")
        )

    def test_branch_content_changes_token(self):
        self.changed(
            lambda value: value[
                "branch_only_messages"
            ][0].update(content="changed")
        )

    def test_message_id_changes_token(self):
        self.changed(
            lambda value: value[
                "branch_only_messages"
            ][0].update(id=22)
        )

    def test_metadata_boolean_changes_token(self):
        self.changed(
            lambda value: value[
                "branch_only_messages"
            ][0].update(
                has_attachment_metadata=True
            )
        )

    def test_last_message_id_changes_token(self):
        self.changed(
            lambda value: value.update(
                expected_branch_last_message_id=22
            )
        )

    def test_already_merged_ids_change_token(self):
        self.changed(
            lambda value: value.update(
                already_merged_source_message_ids=[
                    21
                ]
            )
        )

    def test_token_does_not_call_python_hash(self):
        with patch(
            "builtins.hash",
            side_effect=AssertionError(
                "Python hash() must not be used"
            ),
        ):
            token = self.token()

        self.assertEqual(len(token), 64)


class ComparePreviewTests(
    DisposableDatabaseTestCase
):
    def create_comparable_branch(self):
        parent_id = self.insert_chat("Parent")
        parent_source_id = self.insert_message(
            parent_id,
            "user",
            "Source question",
        )
        parent_only_id = self.insert_message(
            parent_id,
            "assistant",
            "Parent answer",
        )
        branch_id = self.insert_chat(
            "Branch",
            parent_chat_id=parent_id,
            branched_from_message_id=(
                parent_source_id
            ),
        )
        branch_source_id = self.insert_message(
            branch_id,
            "user",
            "Source question",
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET branch_message_id = ?
                WHERE id = ?
                """,
                (branch_source_id, branch_id),
            )

        branch_user_id = self.insert_message(
            branch_id,
            "user",
            "Branch question",
        )
        branch_assistant_id = self.insert_message(
            branch_id,
            "assistant",
            "Branch answer",
        )

        return {
            "parent_id": parent_id,
            "parent_source_id": parent_source_id,
            "parent_only_id": parent_only_id,
            "branch_id": branch_id,
            "branch_source_id": branch_source_id,
            "branch_user_id": branch_user_id,
            "branch_assistant_id": (
                branch_assistant_id
            ),
        }

    def test_comparable_response_includes_preview(self):
        records = self.create_comparable_branch()

        result = (
            history_service
            .compare_chat_with_parent(
                records["branch_id"]
            )
        )

        self.assertTrue(result["comparable"])
        preview = result["merge_preview"]
        self.assertEqual(preview["version"], 1)
        self.assertEqual(
            len(preview["preview_token"]),
            64,
        )
        self.assertEqual(
            preview[
                "expected_parent_last_message_id"
            ],
            records["parent_only_id"],
        )
        self.assertEqual(
            preview[
                "expected_branch_last_message_id"
            ],
            records["branch_assistant_id"],
        )
        self.assertEqual(
            preview["turns"][0]["message_ids"],
            [
                records["branch_user_id"],
                records["branch_assistant_id"],
            ],
        )

    def test_unavailable_response_has_null_preview(self):
        root_id = self.insert_chat("Root")

        result = (
            history_service
            .compare_chat_with_parent(root_id)
        )

        self.assertFalse(result["comparable"])
        self.assertIsNone(result["merge_preview"])

    def test_nested_branch_uses_immediate_parent(self):
        root_id = self.insert_chat("Root")
        root_source_id = self.insert_message(
            root_id,
            "user",
            "Root source",
        )
        middle_id = self.insert_chat(
            "Middle",
            parent_chat_id=root_id,
            branched_from_message_id=root_source_id,
        )
        middle_source_id = self.insert_message(
            middle_id,
            "user",
            "Root source",
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET branch_message_id = ?
                WHERE id = ?
                """,
                (middle_source_id, middle_id),
            )

        nested_parent_boundary = self.insert_message(
            middle_id,
            "user",
            "Middle question",
        )
        middle_after_boundary = self.insert_message(
            middle_id,
            "assistant",
            "Middle answer",
        )
        nested_id = self.insert_chat(
            "Nested",
            parent_chat_id=middle_id,
            branched_from_message_id=(
                nested_parent_boundary
            ),
        )
        nested_source_id = self.insert_message(
            nested_id,
            "user",
            "Middle question",
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET branch_message_id = ?
                WHERE id = ?
                """,
                (nested_source_id, nested_id),
            )

        result = (
            history_service
            .compare_chat_with_parent(nested_id)
        )

        self.assertEqual(
            result["parent_chat"]["id"],
            middle_id,
        )
        self.assertEqual(
            [
                message["id"]
                for message in result[
                    "parent_only_messages"
                ]
            ],
            [middle_after_boundary],
        )

    def test_more_than_one_thousand_messages_untruncated(self):
        records = self.create_comparable_branch()

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        records["branch_id"],
                        "assistant",
                        f"Message {index}",
                        "2026-01-01T00:00:00",
                    )
                    for index in range(1001)
                ],
            )

        result = (
            history_service
            .compare_chat_with_parent(
                records["branch_id"]
            )
        )

        self.assertEqual(
            len(result["branch_only_messages"]),
            1003,
        )
        preview_message_count = sum(
            len(turn["message_ids"])
            for turn in result[
                "merge_preview"
            ]["turns"]
        )
        self.assertEqual(
            preview_message_count,
            1003,
        )

    def test_comparison_creates_no_audit_rows(self):
        records = self.create_comparable_branch()

        history_service.compare_chat_with_parent(
            records["branch_id"]
        )

        with self.connect() as connection:
            operation_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM branch_merge_operations
                """
            ).fetchone()[0]
            mapping_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM branch_merge_message_mappings
                """
            ).fetchone()[0]

        self.assertEqual(operation_count, 0)
        self.assertEqual(mapping_count, 0)

    def test_comparison_locks_already_mapped_turn(self):
        records = self.create_comparable_branch()
        operation_id = self.insert_operation(
            "completed-merge",
            records["branch_id"],
            records["parent_id"],
        )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO branch_merge_message_mappings (
                    merge_operation_id,
                    branch_chat_id,
                    parent_chat_id,
                    turn_key,
                    turn_position,
                    message_position,
                    source_branch_message_id,
                    created_parent_message_id,
                    created_message_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    records["branch_id"],
                    records["parent_id"],
                    (
                        "user:"
                        f"{records['branch_user_id']}"
                    ),
                    0,
                    0,
                    records["branch_user_id"],
                    5000,
                    "fingerprint",
                ),
            )

        result = (
            history_service
            .compare_chat_with_parent(
                records["branch_id"]
            )
        )
        turn = result["merge_preview"][
            "turns"
        ][0]

        self.assertFalse(turn["selectable"])
        self.assertEqual(
            turn["reason"],
            "already_merged",
        )

    def test_response_model_with_and_without_preview(self):
        records = self.create_comparable_branch()
        result = (
            history_service
            .compare_chat_with_parent(
                records["branch_id"]
            )
        )
        with_preview = (
            ChatCompareParentResponse(
                **result
            )
        )
        without_preview = (
            ChatCompareParentResponse(
                comparable=False,
                branch_chat={
                    "id": records["branch_id"],
                    "title": "Branch",
                },
            )
        )

        self.assertIsNotNone(
            with_preview.merge_preview
        )
        self.assertIsNone(
            without_preview.merge_preview
        )


class BranchMergeExecutionTests(
    DisposableDatabaseTestCase
):
    def create_fixture(
        self,
        *,
        turn_count=1,
        source_continuation=False,
        orphan_continuation=False,
        incomplete=False,
    ):
        parent_id = self.insert_chat("Parent")
        parent_source_id = self.insert_message(
            parent_id,
            "user",
            "Shared source prompt",
            created_at="2026-01-01T09:00:00",
        )
        parent_context_id = self.insert_message(
            parent_id,
            "assistant",
            "Existing parent response",
            created_at="2026-01-01T09:01:00",
        )
        branch_id = self.insert_chat(
            "Branch",
            parent_chat_id=parent_id,
            branched_from_message_id=(
                parent_source_id
            ),
        )
        branch_source_id = self.insert_message(
            branch_id,
            "user",
            "Shared source prompt",
            created_at="2026-01-01T09:00:00",
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET branch_message_id = ?
                WHERE id = ?
                """,
                (branch_source_id, branch_id),
            )

        branch_message_ids = []

        if source_continuation:
            branch_message_ids.extend(
                [
                    self.insert_message(
                        branch_id,
                        "assistant",
                        "Copied-prompt answer",
                    ),
                    self.insert_message(
                        branch_id,
                        "system",
                        "Continuation note",
                    ),
                ]
            )

        elif orphan_continuation:
            branch_message_ids.extend(
                [
                    self.insert_message(
                        branch_id,
                        "tool",
                        "Unknown role record",
                    ),
                    self.insert_message(
                        branch_id,
                        "assistant",
                        "Unsafe orphan response",
                    ),
                ]
            )

        elif incomplete:
            branch_message_ids.append(
                self.insert_message(
                    branch_id,
                    "user",
                    "Unanswered prompt",
                )
            )

        else:
            for turn_index in range(
                turn_count
            ):
                branch_message_ids.extend(
                    [
                        self.insert_message(
                            branch_id,
                            "user",
                            (
                                "Branch prompt "
                                f"{turn_index + 1}"
                            ),
                        ),
                        self.insert_message(
                            branch_id,
                            "assistant",
                            (
                                "Branch response "
                                f"{turn_index + 1}"
                            ),
                        ),
                    ]
                )

        return {
            "parent_id": parent_id,
            "parent_source_id": (
                parent_source_id
            ),
            "parent_context_id": (
                parent_context_id
            ),
            "branch_id": branch_id,
            "branch_source_id": (
                branch_source_id
            ),
            "branch_message_ids": (
                branch_message_ids
            ),
        }

    def build_request(
        self,
        fixture,
        *,
        key=None,
        selected_turns=None,
    ):
        comparison = (
            history_service
            .compare_chat_with_parent(
                fixture["branch_id"]
            )
        )
        preview = comparison["merge_preview"]

        if selected_turns is None:
            selected_turns = [
                {
                    "turn_key": turn[
                        "turn_key"
                    ],
                    "message_ids": list(
                        turn["message_ids"]
                    ),
                }
                for turn in preview["turns"]
                if turn["selectable"]
            ]

        request = BranchMergeRequest(
            idempotency_key=(
                key or str(uuid4())
            ),
            preview_token=preview[
                "preview_token"
            ],
            expected={
                "parent_chat_id": comparison[
                    "parent_chat"
                ]["id"],
                "branched_from_message_id": (
                    comparison[
                        "branched_from_message_id"
                    ]
                ),
                "branch_message_id": comparison[
                    "branch_message_id"
                ],
                "parent_last_message_id": (
                    preview[
                        "expected_parent_last_message_id"
                    ]
                ),
                "branch_last_message_id": (
                    preview[
                        "expected_branch_last_message_id"
                    ]
                ),
            },
            selected_turns=selected_turns,
        )
        return request, comparison

    def execute(self, fixture, request):
        return execute_branch_merge(
            self.database_path,
            fixture["branch_id"],
            request,
        )

    def rows(self, sql, parameters=()):
        with self.connect() as connection:
            return connection.execute(
                sql,
                parameters,
            ).fetchall()

    def assert_error(
        self,
        expected_code,
        fixture,
        request,
    ):
        with self.assertRaises(
            BranchMergeError
        ) as raised:
            self.execute(fixture, request)

        self.assertEqual(
            raised.exception.code,
            expected_code,
        )
        return raised.exception

    def test_successful_one_turn_merge(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        response = self.execute(
            fixture,
            request,
        )

        self.assertIsInstance(
            response,
            BranchMergeResponse,
        )
        self.assertEqual(response.status, "completed")
        self.assertFalse(response.replayed)
        self.assertEqual(
            response.inserted_turn_count,
            1,
        )
        self.assertEqual(
            response.inserted_message_count,
            2,
        )
        self.assertEqual(
            response.turns[0]
            .source_branch_message_ids,
            fixture["branch_message_ids"],
        )

    def test_multiple_turns_use_canonical_order(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        _, comparison = self.build_request(
            fixture
        )
        selectable_turns = [
            turn
            for turn in comparison[
                "merge_preview"
            ]["turns"]
            if turn["selectable"]
        ]
        request, _ = self.build_request(
            fixture,
            selected_turns=[
                {
                    "turn_key": turn[
                        "turn_key"
                    ],
                    "message_ids": turn[
                        "message_ids"
                    ],
                }
                for turn in reversed(
                    selectable_turns
                )
            ],
        )

        response = self.execute(
            fixture,
            request,
        )

        self.assertEqual(
            [
                turn.source_branch_message_ids
                for turn in response.turns
            ],
            [
                turn["message_ids"]
                for turn in selectable_turns
            ],
        )

    def test_source_continuation_excludes_source(self):
        fixture = self.create_fixture(
            source_continuation=True
        )
        request, _ = self.build_request(
            fixture
        )

        response = self.execute(
            fixture,
            request,
        )

        source_ids = response.turns[0]
        self.assertEqual(
            source_ids.turn_key,
            f"source:{fixture['branch_source_id']}",
        )
        self.assertNotIn(
            fixture["branch_source_id"],
            source_ids.source_branch_message_ids,
        )
        self.assertEqual(
            source_ids.source_branch_message_ids,
            fixture["branch_message_ids"],
        )

    def test_nested_branch_targets_immediate_parent(self):
        fixture = self.create_fixture()
        root_id = self.insert_chat("Root")
        root_source_id = self.insert_message(
            root_id,
            "user",
            "Root source",
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET
                    parent_chat_id = ?,
                    branched_from_message_id = ?,
                    branch_message_id = ?
                WHERE id = ?
                """,
                (
                    root_id,
                    root_source_id,
                    fixture["parent_source_id"],
                    fixture["parent_id"],
                ),
            )

        request, _ = self.build_request(
            fixture
        )
        root_count_before = len(
            self.rows(
                "SELECT id FROM messages WHERE chat_id = ?",
                (root_id,),
            )
        )
        response = self.execute(
            fixture,
            request,
        )

        self.assertEqual(
            response.parent_chat_id,
            fixture["parent_id"],
        )
        self.assertEqual(
            len(
                self.rows(
                    "SELECT id FROM messages WHERE chat_id = ?",
                    (root_id,),
                )
            ),
            root_count_before,
        )

    def test_source_and_existing_parent_rows_unchanged(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        branch_before = self.rows(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (fixture["branch_id"],),
        )
        parent_before = self.rows(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (fixture["parent_id"],),
        )

        self.execute(fixture, request)

        branch_after = self.rows(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (fixture["branch_id"],),
        )
        parent_after = self.rows(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (fixture["parent_id"],),
        )
        self.assertEqual(branch_after, branch_before)
        self.assertEqual(
            parent_after[:len(parent_before)],
            parent_before,
        )

    def test_inserted_messages_use_safe_fields(self):
        fixture = self.create_fixture()

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE messages
                SET
                    sources_json = ?,
                    attachment_json = ?,
                    model_id = ?
                WHERE chat_id = ?
                  AND id > ?
                """,
                (
                    '[{"title":"secret"}]',
                    '{"filename":"secret.pdf"}',
                    "source-model",
                    fixture["branch_id"],
                    fixture["branch_source_id"],
                ),
            )

        request, _ = self.build_request(
            fixture
        )
        response = self.execute(
            fixture,
            request,
        )
        inserted_rows = self.rows(
            """
            SELECT
                role,
                content,
                created_at,
                sources_json,
                model_id,
                attachment_json
            FROM messages
            WHERE id BETWEEN ? AND ?
            ORDER BY id
            """,
            (
                response.first_created_parent_message_id,
                response.last_created_parent_message_id,
            ),
        )
        source_rows = self.rows(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE id IN (?, ?)
            ORDER BY id
            """,
            tuple(fixture["branch_message_ids"]),
        )

        self.assertEqual(
            [row[:2] for row in inserted_rows],
            [row[:2] for row in source_rows],
        )
        self.assertEqual(
            len({row[2] for row in inserted_rows}),
            1,
        )
        self.assertNotEqual(
            inserted_rows[0][2],
            source_rows[0][2],
        )

        for row in inserted_rows:
            self.assertEqual(row[3], "[]")
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])

    def test_empty_selection_has_zero_writes(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture,
            selected_turns=[],
        )
        parent_count = len(
            self.rows(
                "SELECT id FROM messages WHERE chat_id = ?",
                (fixture["parent_id"],),
            )
        )

        self.assert_error(
            "EMPTY_SELECTION",
            fixture,
            request,
        )

        self.assertEqual(
            len(
                self.rows(
                    "SELECT id FROM messages WHERE chat_id = ?",
                    (fixture["parent_id"],),
                )
            ),
            parent_count,
        )
        self.assertEqual(
            self.rows(
                "SELECT id FROM branch_merge_operations"
            ),
            [],
        )

    def test_invalid_turn_has_zero_writes(self):
        fixture = self.create_fixture()
        request, comparison = self.build_request(
            fixture
        )
        canonical_ids = comparison[
            "merge_preview"
        ]["turns"][0]["message_ids"]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": "user:999999",
                        "message_ids": canonical_ids,
                    }
                ],
            }
        )

        self.assert_error(
            "INVALID_SELECTED_TURN",
            fixture,
            request,
        )
        self.assertEqual(
            self.rows(
                "SELECT id FROM branch_merge_operations"
            ),
            [],
        )

    def test_orphan_turn_is_rejected(self):
        fixture = self.create_fixture(
            orphan_continuation=True
        )
        _, comparison = self.build_request(
            fixture
        )
        orphan_turn = next(
            turn
            for turn in comparison[
                "merge_preview"
            ]["turns"]
            if turn["reason"]
            == "orphan_messages"
        )
        request, _ = self.build_request(
            fixture,
            selected_turns=[
                {
                    "turn_key": orphan_turn[
                        "turn_key"
                    ],
                    "message_ids": orphan_turn[
                        "message_ids"
                    ],
                }
            ],
        )

        self.assert_error(
            "ORPHAN_SELECTED_MESSAGE",
            fixture,
            request,
        )

    def test_incomplete_turn_is_rejected(self):
        fixture = self.create_fixture(
            incomplete=True
        )
        _, comparison = self.build_request(
            fixture
        )
        incomplete_turn = comparison[
            "merge_preview"
        ]["turns"][0]
        request, _ = self.build_request(
            fixture,
            selected_turns=[
                {
                    "turn_key": incomplete_turn[
                        "turn_key"
                    ],
                    "message_ids": incomplete_turn[
                        "message_ids"
                    ],
                }
            ],
        )

        self.assert_error(
            "INVALID_SELECTED_TURN",
            fixture,
            request,
        )

    def test_duplicate_turn_key_is_rejected(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        request, comparison = self.build_request(
            fixture
        )
        first_turn = comparison[
            "merge_preview"
        ]["turns"][0]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": first_turn[
                            "turn_key"
                        ],
                        "message_ids": first_turn[
                            "message_ids"
                        ],
                    },
                    {
                        "turn_key": first_turn[
                            "turn_key"
                        ],
                        "message_ids": first_turn[
                            "message_ids"
                        ],
                    },
                ],
            }
        )

        self.assert_error(
            "INVALID_SELECTED_TURN",
            fixture,
            request,
        )

    def test_duplicate_selected_id_is_rejected(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        request, comparison = self.build_request(
            fixture
        )
        first_turn, second_turn = comparison[
            "merge_preview"
        ]["turns"]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": first_turn[
                            "turn_key"
                        ],
                        "message_ids": first_turn[
                            "message_ids"
                        ],
                    },
                    {
                        "turn_key": second_turn[
                            "turn_key"
                        ],
                        "message_ids": [
                            first_turn[
                                "message_ids"
                            ][0],
                            second_turn[
                                "message_ids"
                            ][1],
                        ],
                    },
                ],
            }
        )

        self.assert_error(
            "DUPLICATE_SELECTED_ID",
            fixture,
            request,
        )

    def test_message_owned_by_other_chat_is_rejected(self):
        fixture = self.create_fixture()
        request, comparison = self.build_request(
            fixture
        )
        other_chat_id = self.insert_chat("Other")
        other_message_id = self.insert_message(
            other_chat_id,
            "user",
            "Other message",
        )
        canonical_turn = comparison[
            "merge_preview"
        ]["turns"][0]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": canonical_turn[
                            "turn_key"
                        ],
                        "message_ids": [
                            other_message_id
                        ],
                    }
                ],
            }
        )

        self.assert_error(
            "MESSAGE_NOT_OWNED_BY_BRANCH",
            fixture,
            request,
        )

    def test_boundary_message_is_rejected(self):
        fixture = self.create_fixture()
        request, comparison = self.build_request(
            fixture
        )
        canonical_turn = comparison[
            "merge_preview"
        ]["turns"][0]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": canonical_turn[
                            "turn_key"
                        ],
                        "message_ids": [
                            fixture[
                                "branch_source_id"
                            ]
                        ],
                    }
                ],
            }
        )

        self.assert_error(
            "MESSAGE_OUTSIDE_BRANCH_CONTINUATION",
            fixture,
            request,
        )

    def test_noncanonical_payload_is_rejected(self):
        fixture = self.create_fixture()
        request, comparison = self.build_request(
            fixture
        )
        canonical_turn = comparison[
            "merge_preview"
        ]["turns"][0]
        request = BranchMergeRequest(
            **{
                **request.model_dump(),
                "selected_turns": [
                    {
                        "turn_key": canonical_turn[
                            "turn_key"
                        ],
                        "message_ids": canonical_turn[
                            "message_ids"
                        ][:1],
                    }
                ],
            }
        )

        self.assert_error(
            "INVALID_SELECTED_TURN",
            fixture,
            request,
        )

    def test_parent_change_makes_preview_stale(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        self.insert_message(
            fixture["parent_id"],
            "assistant",
            "Later parent message",
        )

        error = self.assert_error(
            "STALE_PREVIEW",
            fixture,
            request,
        )
        self.assertTrue(error.refresh_preview)

    def test_branch_change_makes_preview_stale(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        self.insert_message(
            fixture["branch_id"],
            "assistant",
            "Later branch message",
        )

        self.assert_error(
            "STALE_PREVIEW",
            fixture,
            request,
        )

    def test_parent_relationship_change_is_stale(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        replacement_parent = self.insert_chat(
            "Replacement"
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET parent_chat_id = ?
                WHERE id = ?
                """,
                (
                    replacement_parent,
                    fixture["branch_id"],
                ),
            )

        self.assert_error(
            "STALE_PREVIEW",
            fixture,
            request,
        )

    def test_deleted_boundary_is_safely_rejected(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with self.connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE id = ?",
                (fixture["parent_source_id"],),
            )

        self.assert_error(
            "INVALID_BRANCH_BOUNDARY",
            fixture,
            request,
        )

    def test_same_key_replays_exact_response(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        request, _ = self.build_request(
            fixture
        )
        first = self.execute(fixture, request)
        parent_count_after_first = len(
            self.rows(
                "SELECT id FROM messages WHERE chat_id = ?",
                (fixture["parent_id"],),
            )
        )
        replay = self.execute(fixture, request)

        first_payload = first.model_dump()
        replay_payload = replay.model_dump()
        first_payload["replayed"] = True
        self.assertEqual(replay_payload, first_payload)
        self.assertEqual(
            len(
                self.rows(
                    "SELECT id FROM messages WHERE chat_id = ?",
                    (fixture["parent_id"],),
                )
            ),
            parent_count_after_first,
        )

    def test_reused_key_with_changed_request_is_rejected(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        self.execute(fixture, request)
        changed_payload = request.model_dump()
        changed_payload["preview_token"] = "a" * 64
        changed_request = BranchMergeRequest(
            **changed_payload
        )

        self.assert_error(
            "IDEMPOTENCY_KEY_REUSED",
            fixture,
            changed_request,
        )

    def test_different_key_cannot_merge_mapped_source(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        first = self.execute(fixture, request)
        new_payload = request.model_dump()
        new_payload["idempotency_key"] = str(
            uuid4()
        )
        second_request = BranchMergeRequest(
            **new_payload
        )

        error = self.assert_error(
            "MERGE_ALREADY_COMPLETED",
            fixture,
            second_request,
        )
        self.assertEqual(
            error.operation_id,
            first.operation_id,
        )

    def test_audit_operation_and_mappings_are_complete(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        request, _ = self.build_request(
            fixture
        )
        response = self.execute(
            fixture,
            request,
        )
        operation = self.rows(
            """
            SELECT
                status,
                inserted_turn_count,
                inserted_message_count,
                first_created_parent_message_id,
                last_created_parent_message_id,
                completed_at,
                request_fingerprint
            FROM branch_merge_operations
            WHERE id = ?
            """,
            (response.operation_id,),
        )[0]
        mappings = self.rows(
            """
            SELECT
                turn_key,
                turn_position,
                message_position,
                source_branch_message_id,
                created_parent_message_id,
                created_message_fingerprint
            FROM branch_merge_message_mappings
            WHERE merge_operation_id = ?
            ORDER BY turn_position, message_position
            """,
            (response.operation_id,),
        )

        self.assertEqual(operation[0], "completed")
        self.assertEqual(
            operation[1:6],
            (
                response.inserted_turn_count,
                response.inserted_message_count,
                response.first_created_parent_message_id,
                response.last_created_parent_message_id,
                response.completed_at,
            ),
        )
        self.assertEqual(
            operation[6],
            _build_branch_merge_request_fingerprint(
                fixture["branch_id"],
                request,
            ),
        )
        self.assertEqual(
            [row[3] for row in mappings],
            fixture["branch_message_ids"],
        )
        self.assertEqual(
            [row[4] for row in mappings],
            [
                message_id
                for turn in response.turns
                for message_id in turn
                .created_parent_message_ids
            ],
        )

        for mapping in mappings:
            created_row = self.rows(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE id = ?
                """,
                (mapping[4],),
            )[0]
            expected_fingerprint = (
                _canonical_sha256(
                    {
                        "role": created_row[0],
                        "content": created_row[1],
                        "created_at": created_row[2],
                    }
                )
            )
            self.assertEqual(
                mapping[5],
                expected_fingerprint,
            )

    def test_forced_partial_failure_rolls_back_all(self):
        fixture = self.create_fixture(
            turn_count=2
        )
        request, _ = self.build_request(
            fixture
        )
        parent_before = self.rows(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
            (fixture["parent_id"],),
        )
        original_insert = (
            branch_merge_service
            ._insert_parent_message
        )
        call_count = 0

        def insert_then_fail(*arguments):
            nonlocal call_count
            call_count += 1
            created_id = original_insert(
                *arguments
            )

            if call_count == 2:
                raise RuntimeError(
                    "forced test failure"
                )

            return created_id

        with patch.object(
            branch_merge_service,
            "_insert_parent_message",
            side_effect=insert_then_fail,
        ):
            self.assert_error(
                "MERGE_FAILED",
                fixture,
                request,
            )

        self.assertEqual(
            self.rows(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
                (fixture["parent_id"],),
            ),
            parent_before,
        )
        self.assertEqual(
            self.rows(
                "SELECT id FROM branch_merge_operations"
            ),
            [],
        )
        self.assertEqual(
            self.rows(
                "SELECT id FROM branch_merge_message_mappings"
            ),
            [],
        )

    def test_more_than_one_thousand_messages_merge(self):
        fixture = self.create_fixture(
            incomplete=True
        )

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO messages (
                    chat_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, 'assistant', ?, ?)
                """,
                [
                    (
                        fixture["branch_id"],
                        f"Large response {index}",
                        "2026-01-01T10:00:00",
                    )
                    for index in range(1000)
                ],
            )

        request, _ = self.build_request(
            fixture
        )
        response = self.execute(
            fixture,
            request,
        )

        self.assertEqual(
            response.inserted_message_count,
            1001,
        )
        self.assertEqual(
            len(
                response.turns[0]
                .source_branch_message_ids
            ),
            1001,
        )

    def test_documents_bookmarks_and_branch_metadata_unchanged(self):
        fixture = self.create_fixture()

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO message_bookmarks (
                    chat_id,
                    message_id,
                    note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fixture["branch_id"],
                    fixture[
                        "branch_message_ids"
                    ][0],
                    "Keep bookmark",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO documents (
                    document_id,
                    chat_id,
                    filename,
                    file_path,
                    file_hash,
                    uploaded_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "document-1",
                    fixture["branch_id"],
                    "source.pdf",
                    "not-a-real-file",
                    "hash",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )

        bookmark_before = self.rows(
            "SELECT * FROM message_bookmarks"
        )
        document_before = self.rows(
            "SELECT * FROM documents"
        )
        branch_metadata_before = self.rows(
            "SELECT * FROM chats WHERE id = ?",
            (fixture["branch_id"],),
        )
        folders_before = self.rows(
            "SELECT * FROM folders"
        )
        request, _ = self.build_request(
            fixture
        )

        self.execute(fixture, request)

        self.assertEqual(
            self.rows(
                "SELECT * FROM message_bookmarks"
            ),
            bookmark_before,
        )
        self.assertEqual(
            self.rows("SELECT * FROM documents"),
            document_before,
        )
        self.assertEqual(
            self.rows(
                "SELECT * FROM chats WHERE id = ?",
                (fixture["branch_id"],),
            ),
            branch_metadata_before,
        )
        self.assertEqual(
            self.rows("SELECT * FROM folders"),
            folders_before,
        )

    def test_request_and_response_validation(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        payload = request.model_dump()

        with self.assertRaises(ValidationError):
            BranchMergeRequest(
                **{
                    **payload,
                    "idempotency_key": "not-a-uuid",
                }
            )

        with self.assertRaises(ValidationError):
            BranchMergeRequest(
                **{
                    **payload,
                    "preview_token": "A" * 64,
                }
            )

        with self.assertRaises(ValidationError):
            BranchMergeRequest(
                **{
                    **payload,
                    "content": "must not be accepted",
                }
            )

        with self.assertRaises(ValidationError):
            BranchMergeRequest(
                **{
                    **payload,
                    "selected_turns": [
                        {
                            "turn_key": "user:1",
                            "message_ids": [True],
                        }
                    ],
                }
            )

        response = self.execute(
            fixture,
            request,
        )
        self.assertEqual(
            BranchMergeResponse.model_validate(
                response.model_dump()
            ),
            response,
        )

    def test_request_fingerprint_excludes_key(self):
        fixture = self.create_fixture()
        first, _ = self.build_request(
            fixture
        )
        second_payload = first.model_dump()
        second_payload["idempotency_key"] = str(
            uuid4()
        )
        second = BranchMergeRequest(
            **second_payload
        )

        self.assertEqual(
            _build_branch_merge_request_fingerprint(
                fixture["branch_id"],
                first,
            ),
            _build_branch_merge_request_fingerprint(
                fixture["branch_id"],
                second,
            ),
        )

    def test_busy_error_is_translated(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with patch.object(
            branch_merge_service,
            "get_connection",
            side_effect=sqlite3.OperationalError(
                "database is locked"
            ),
        ):
            error = self.assert_error(
                "MERGE_BUSY",
                fixture,
                request,
            )

        self.assertEqual(error.http_status, 503)
        self.assertTrue(error.retryable)

    def test_missing_branch_is_not_found(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with self.assertRaises(
            BranchMergeError
        ) as raised:
            execute_branch_merge(
                self.database_path,
                999999,
                request,
            )

        self.assertEqual(
            raised.exception.code,
            "BRANCH_NOT_FOUND",
        )

    def test_detached_branch_is_rejected(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET parent_chat_id = NULL
                WHERE id = ?
                """,
                (fixture["branch_id"],),
            )

        self.assert_error(
            "DETACHED_BRANCH",
            fixture,
            request,
        )

    def test_missing_parent_is_rejected(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with self.connect() as connection:
            connection.execute(
                "DELETE FROM chats WHERE id = ?",
                (fixture["parent_id"],),
            )

        self.assert_error(
            "PARENT_MISSING",
            fixture,
            request,
        )

    def test_non_user_boundary_is_rejected(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE messages
                SET role = 'assistant'
                WHERE id = ?
                """,
                (fixture["parent_source_id"],),
            )

        self.assert_error(
            "INVALID_BRANCH_BOUNDARY",
            fixture,
            request,
        )

    def test_concurrent_same_key_completes_and_replays(self):
        fixture = self.create_fixture()
        request, _ = self.build_request(
            fixture
        )
        barrier = threading.Barrier(2)

        def run_merge():
            barrier.wait()
            return self.execute(
                fixture,
                request,
            )

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            results = list(
                executor.map(
                    lambda _: run_merge(),
                    range(2),
                )
            )

        self.assertEqual(
            sorted(
                result.replayed
                for result in results
            ),
            [False, True],
        )
        self.assertEqual(
            len(
                self.rows(
                    "SELECT id FROM branch_merge_operations"
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.rows(
                    """
                    SELECT id
                    FROM branch_merge_message_mappings
                    """
                )
            ),
            2,
        )

    def test_concurrent_different_keys_do_not_duplicate(self):
        fixture = self.create_fixture()
        first_request, _ = self.build_request(
            fixture
        )
        second_payload = (
            first_request.model_dump()
        )
        second_payload["idempotency_key"] = str(
            uuid4()
        )
        second_request = BranchMergeRequest(
            **second_payload
        )
        barrier = threading.Barrier(2)

        def run_merge(request):
            barrier.wait()

            try:
                return self.execute(
                    fixture,
                    request,
                )
            except BranchMergeError as error:
                return error

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            results = list(
                executor.map(
                    run_merge,
                    [
                        first_request,
                        second_request,
                    ],
                )
            )

        responses = [
            result
            for result in results
            if isinstance(
                result,
                BranchMergeResponse,
            )
        ]
        errors = [
            result
            for result in results
            if isinstance(
                result,
                BranchMergeError,
            )
        ]
        self.assertEqual(len(responses), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn(
            errors[0].code,
            {
                "MERGE_ALREADY_COMPLETED",
                "STALE_PREVIEW",
            },
        )
        self.assertEqual(
            len(
                self.rows(
                    "SELECT id FROM branch_merge_operations"
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                self.rows(
                    """
                    SELECT id
                    FROM branch_merge_message_mappings
                    """
                )
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
