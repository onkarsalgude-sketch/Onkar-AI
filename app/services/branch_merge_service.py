"""Canonical preview and internal execution helpers for safe branch merges.

The preview token produced here is a version and staleness token. It is not an
authentication credential. Any future public merge endpoint must require
authorization plus CSRF/origin protection, reload all authoritative records
inside its transaction, and never trust client-provided content, roles,
timestamps, or destination ownership.

Snapshot and canonicalization helpers are pure or cursor-level. The internal
execution entry point opens exactly one connection and owns one transaction.
"""

import hashlib
import json
import sqlite3
from datetime import datetime

from app.database.db import (
    DATABASE_INTEGRITY_ERRORS,
    DATABASE_OPERATIONAL_ERRORS,
    acquire_branch_merge_lock,
    begin_write_transaction,
    configure_busy_timeout,
    get_runtime_connection as get_connection,
    is_database_busy_error,
)
from app.models.chat import (
    BranchMergeRequest,
    BranchMergeResponse,
    BranchMergeTurnResult,
)


BRANCH_MERGE_PREVIEW_VERSION = 1

_ALLOWED_MESSAGE_ROLES = {
    "user",
    "assistant",
    "system",
}

_PREVIEW_RECORD_FIELDS = (
    "id",
    "role",
    "content",
    "created_at",
    "has_attachment_metadata",
    "has_source_metadata",
)


class BranchMergeError(Exception):
    """Safe, structured failure from internal branch merge execution."""

    def __init__(
        self,
        code,
        message,
        *,
        http_status,
        retryable=False,
        refresh_preview=False,
        operation_id=None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.refresh_preview = (
            refresh_preview
        )
        self.operation_id = operation_id

    def as_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "refresh_preview": (
                self.refresh_preview
            ),
            "operation_id": self.operation_id,
        }


def _is_positive_integer(value):
    """Return whether value is a real, strictly positive integer."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def _canonical_json_bytes(value):
    """Serialize a JSON-compatible value deterministically as UTF-8."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value):
    """Return the lowercase SHA-256 hex digest of a canonical JSON value."""
    return hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()


def _locked_unit(
    turn_key,
    message_ids,
    reason,
):
    return {
        "turn_key": turn_key,
        "type": "locked",
        "selectable": False,
        "anchor_message_id": None,
        "message_ids": message_ids,
        "reason": reason,
    }


def _selectable_unit(
    turn_key,
    unit_type,
    anchor_message_id,
    message_ids,
    already_merged_message_ids,
    *,
    incomplete=False,
):
    reason = None
    selectable = True

    if any(
        message_id in already_merged_message_ids
        for message_id in message_ids
    ):
        selectable = False
        reason = "already_merged"

    elif incomplete:
        selectable = False
        reason = "incomplete_turn"

    return {
        "turn_key": turn_key,
        "type": unit_type,
        "selectable": selectable,
        "anchor_message_id": anchor_message_id,
        "message_ids": message_ids,
        "reason": reason,
    }


def _build_canonical_branch_turns(
    branch_message_id,
    branch_source_message,
    branch_only_messages,
    already_merged_source_message_ids,
):
    """Build deterministic, ID-based branch continuation units.

    Message content and timestamps are intentionally ignored. The database's
    ascending message-ID order and exact roles are the only grouping inputs.
    """
    already_merged_message_ids = {
        value
        for value in already_merged_source_message_ids
        if _is_positive_integer(value)
    }

    source_is_exact_user = (
        _is_positive_integer(branch_message_id)
        and isinstance(branch_source_message, dict)
        and branch_source_message.get("id")
        == branch_message_id
        and branch_source_message.get("role")
        == "user"
    )

    records_by_id = {}
    invalid_record_count = 0

    for message in branch_only_messages:
        if not isinstance(message, dict):
            invalid_record_count += 1
            continue

        message_id = message.get("id")

        if not _is_positive_integer(message_id):
            invalid_record_count += 1
            continue

        records_by_id.setdefault(
            message_id,
            [],
        ).append(message)

    ordered_entries = []

    for message_id in sorted(records_by_id):
        records = records_by_id[message_id]

        if len(records) > 1:
            ordered_entries.append(
                {
                    "kind": "duplicate",
                    "id": message_id,
                }
            )
            continue

        role = records[0].get("role")

        ordered_entries.append(
            {
                "kind": (
                    "message"
                    if role in _ALLOWED_MESSAGE_ROLES
                    else "unknown"
                ),
                "id": message_id,
                "role": role,
            }
        )

    units = []
    current_turn = None
    leading_messages = []
    orphan_messages = []
    is_leading = True

    def flush_current_turn(*, final=False):
        nonlocal current_turn

        if current_turn is None:
            return

        message_ids = current_turn["message_ids"]

        units.append(
            _selectable_unit(
                current_turn["turn_key"],
                "turn",
                current_turn[
                    "anchor_message_id"
                ],
                message_ids,
                already_merged_message_ids,
                incomplete=(
                    final
                    and len(message_ids) == 1
                ),
            )
        )
        current_turn = None

    def flush_leading_messages():
        nonlocal leading_messages

        if not leading_messages:
            return

        if source_is_exact_user:
            units.append(
                _selectable_unit(
                    (
                        "source:"
                        f"{branch_message_id}"
                    ),
                    "source",
                    branch_message_id,
                    leading_messages,
                    already_merged_message_ids,
                )
            )
        else:
            units.append(
                _locked_unit(
                    (
                        "locked:orphan:"
                        f"{leading_messages[0]}"
                    ),
                    leading_messages,
                    "orphan_messages",
                )
            )

        leading_messages = []

    def flush_orphan_messages():
        nonlocal orphan_messages

        if not orphan_messages:
            return

        units.append(
            _locked_unit(
                (
                    "locked:orphan:"
                    f"{orphan_messages[0]}"
                ),
                orphan_messages,
                "orphan_messages",
            )
        )
        orphan_messages = []

    def flush_open_units(*, final_turn=False):
        flush_current_turn(final=final_turn)
        flush_leading_messages()
        flush_orphan_messages()

    for entry in ordered_entries:
        entry_kind = entry["kind"]
        message_id = entry["id"]

        if entry_kind == "duplicate":
            flush_open_units()
            units.append(
                _locked_unit(
                    (
                        "locked:duplicate:"
                        f"{message_id}"
                    ),
                    [],
                    "duplicate_message_id",
                )
            )
            is_leading = False
            continue

        if entry_kind == "unknown":
            flush_open_units()
            units.append(
                _locked_unit(
                    (
                        "locked:unknown:"
                        f"{message_id}"
                    ),
                    [message_id],
                    "unknown_role",
                )
            )
            is_leading = False
            continue

        role = entry["role"]

        if role == "user":
            flush_open_units()
            current_turn = {
                "turn_key": (
                    f"user:{message_id}"
                ),
                "anchor_message_id": (
                    message_id
                ),
                "message_ids": [message_id],
            }
            is_leading = False
            continue

        if is_leading:
            leading_messages.append(
                message_id
            )
            continue

        if current_turn is not None:
            current_turn[
                "message_ids"
            ].append(message_id)
            continue

        flush_leading_messages()
        orphan_messages.append(message_id)

    flush_open_units(final_turn=True)

    if invalid_record_count:
        units.append(
            _locked_unit(
                "locked:invalid_message_id",
                [],
                "invalid_message_id",
            )
        )

    return units


def _preview_record(record):
    if record is None:
        return None

    return {
        field: record.get(field)
        for field in _PREVIEW_RECORD_FIELDS
    }


def _preview_turn(turn):
    return {
        "turn_key": turn.get("turn_key"),
        "type": turn.get("type"),
        "selectable": turn.get(
            "selectable"
        ),
        "anchor_message_id": turn.get(
            "anchor_message_id"
        ),
        "message_ids": list(
            turn.get("message_ids", [])
        ),
        "reason": turn.get("reason"),
    }


def _build_branch_merge_preview_token(
    *,
    version,
    branch_chat_id,
    branch_chat_title,
    parent_chat_id,
    parent_chat_title,
    branched_from_message_id,
    branch_message_id,
    parent_source_message,
    branch_source_message,
    parent_only_messages,
    branch_only_messages,
    expected_parent_last_message_id,
    expected_branch_last_message_id,
    already_merged_source_message_ids,
    turns,
):
    """Hash the complete authoritative merge-preview snapshot."""
    payload = {
        "version": version,
        "branch_chat": {
            "id": branch_chat_id,
            "title": branch_chat_title,
        },
        "parent_chat": {
            "id": parent_chat_id,
            "title": parent_chat_title,
        },
        "branched_from_message_id": (
            branched_from_message_id
        ),
        "branch_message_id": branch_message_id,
        "parent_source_message": (
            _preview_record(
                parent_source_message
            )
        ),
        "branch_source_message": (
            _preview_record(
                branch_source_message
            )
        ),
        "parent_only_messages": [
            _preview_record(message)
            for message in parent_only_messages
        ],
        "branch_only_messages": [
            _preview_record(message)
            for message in branch_only_messages
        ],
        "expected_parent_last_message_id": (
            expected_parent_last_message_id
        ),
        "expected_branch_last_message_id": (
            expected_branch_last_message_id
        ),
        "already_merged_source_message_ids": (
            sorted(
                already_merged_source_message_ids
            )
        ),
        "turns": [
            _preview_turn(turn)
            for turn in turns
        ],
    }

    return _canonical_sha256(payload)


def _has_meaningful_json_metadata(value):
    if value is None:
        return False

    try:
        if isinstance(value, (bytes, bytearray)):
            text = bytes(value).decode(
                "utf-8"
            ).strip()
        else:
            text = str(value).strip()
    except Exception:
        return True

    if not text:
        return False

    try:
        parsed_value = json.loads(text)
    except Exception:
        return True

    if parsed_value is None:
        return False

    if isinstance(
        parsed_value,
        (dict, list, str),
    ):
        return bool(parsed_value)

    return True


def _comparison_message(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "has_source_metadata": (
            _has_meaningful_json_metadata(
                row["sources_json"]
            )
        ),
        "has_attachment_metadata": (
            _has_meaningful_json_metadata(
                row["attachment_json"]
            )
        ),
    }


def _load_message_range(
    cursor,
    chat_id,
    operator,
    boundary_message_id,
):
    if operator not in {"<=", ">"}:
        raise ValueError(
            "Invalid message range operator."
        )

    cursor.execute(
        f"""
        SELECT
            id,
            role,
            content,
            created_at,
            sources_json,
            attachment_json
        FROM messages
        WHERE chat_id = ?
          AND id {operator} ?
        ORDER BY id ASC
        """,
        (
            chat_id,
            boundary_message_id,
        ),
    )

    return [
        _comparison_message(row)
        for row in cursor.fetchall()
    ]


def _load_authoritative_merge_snapshot(
    cursor,
    branch_chat_id,
    expected_state=None,
):
    cursor.execute(
        """
        SELECT
            branch_chats.id AS branch_chat_id,
            branch_chats.title AS branch_chat_title,
            branch_chats.parent_chat_id AS stored_parent_chat_id,
            branch_chats.branched_from_message_id,
            branch_chats.branch_message_id,
            parent_chats.id AS resolved_parent_chat_id,
            parent_chats.title AS parent_chat_title
        FROM chats AS branch_chats
        LEFT JOIN chats AS parent_chats
            ON parent_chats.id = branch_chats.parent_chat_id
        WHERE branch_chats.id = ?
        """,
        (branch_chat_id,),
    )
    chat_row = cursor.fetchone()

    if chat_row is None:
        raise BranchMergeError(
            "BRANCH_NOT_FOUND",
            "The requested branch chat was not found.",
            http_status=404,
        )

    stored_parent_chat_id = chat_row[
        "stored_parent_chat_id"
    ]

    if not _is_positive_integer(
        stored_parent_chat_id
    ):
        raise BranchMergeError(
            "DETACHED_BRANCH",
            "This branch is no longer attached to a parent chat.",
            http_status=409,
            refresh_preview=True,
        )

    if chat_row[
        "resolved_parent_chat_id"
    ] is None:
        raise BranchMergeError(
            "PARENT_MISSING",
            "The immediate parent chat is unavailable.",
            http_status=409,
            refresh_preview=True,
        )

    resolved_parent_chat_id = chat_row[
        "resolved_parent_chat_id"
    ]

    if not _is_positive_integer(
        resolved_parent_chat_id
    ):
        raise BranchMergeError(
            "PARENT_MISSING",
            "The immediate parent chat is unavailable.",
            http_status=409,
            refresh_preview=True,
        )

    parent_message_id = chat_row[
        "branched_from_message_id"
    ]
    branch_message_id = chat_row[
        "branch_message_id"
    ]

    if (
        not _is_positive_integer(
            parent_message_id
        )
        or not _is_positive_integer(
            branch_message_id
        )
    ):
        raise BranchMergeError(
            "INVALID_BRANCH_BOUNDARY",
            "The branch boundary metadata is unavailable or invalid.",
            http_status=409,
            refresh_preview=True,
        )

    if (
        expected_state is not None
        and (
            resolved_parent_chat_id,
            parent_message_id,
            branch_message_id,
        )
        != (
            expected_state.parent_chat_id,
            expected_state.branched_from_message_id,
            expected_state.branch_message_id,
        )
    ):
        raise BranchMergeError(
            "STALE_PREVIEW",
            "The branch or parent changed. Refresh the merge preview.",
            http_status=409,
            refresh_preview=True,
        )

    def load_source_message(
        message_id,
        chat_id,
    ):
        cursor.execute(
            """
            SELECT
                id,
                role,
                content,
                created_at,
                sources_json,
                attachment_json
            FROM messages
            WHERE id = ?
              AND chat_id = ?
            """,
            (
                message_id,
                chat_id,
            ),
        )
        return _comparison_message(
            cursor.fetchone()
        )

    parent_source_message = (
        load_source_message(
            parent_message_id,
            resolved_parent_chat_id,
        )
    )
    branch_source_message = (
        load_source_message(
            branch_message_id,
            branch_chat_id,
        )
    )

    if (
        parent_source_message is None
        or branch_source_message is None
        or parent_source_message["role"]
        != "user"
        or branch_source_message["role"]
        != "user"
    ):
        raise BranchMergeError(
            "INVALID_BRANCH_BOUNDARY",
            "The exact user-message branch boundary is unavailable.",
            http_status=409,
            refresh_preview=True,
        )

    parent_only_messages = (
        _load_message_range(
            cursor,
            resolved_parent_chat_id,
            ">",
            parent_message_id,
        )
    )
    branch_only_messages = (
        _load_message_range(
            cursor,
            branch_chat_id,
            ">",
            branch_message_id,
        )
    )

    cursor.execute(
        """
        SELECT
            source_branch_message_id,
            merge_operation_id
        FROM branch_merge_message_mappings
        WHERE branch_chat_id = ?
          AND parent_chat_id = ?
        ORDER BY source_branch_message_id ASC
        """,
        (
            branch_chat_id,
            resolved_parent_chat_id,
        ),
    )
    mapping_rows = cursor.fetchall()
    already_merged_operation_by_message = {}

    for mapping_row in mapping_rows:
        source_message_id = mapping_row[
            "source_branch_message_id"
        ]
        operation_id = mapping_row[
            "merge_operation_id"
        ]

        if (
            not _is_positive_integer(
                source_message_id
            )
            or not _is_positive_integer(
                operation_id
            )
        ):
            raise BranchMergeError(
                "MERGE_FAILED",
                "Stored merge audit data is invalid.",
                http_status=500,
            )

        already_merged_operation_by_message[
            source_message_id
        ] = operation_id

    already_merged_message_ids = sorted(
        already_merged_operation_by_message
    )

    cursor.execute(
        """
        SELECT COALESCE(MAX(id), 0) AS last_message_id
        FROM messages
        WHERE chat_id = ?
        """,
        (resolved_parent_chat_id,),
    )
    parent_last_message_id = cursor.fetchone()[
        "last_message_id"
    ]

    cursor.execute(
        """
        SELECT COALESCE(MAX(id), 0) AS last_message_id
        FROM messages
        WHERE chat_id = ?
        """,
        (branch_chat_id,),
    )
    branch_last_message_id = cursor.fetchone()[
        "last_message_id"
    ]

    if (
        not _is_positive_integer(
            parent_last_message_id
        )
        or not _is_positive_integer(
            branch_last_message_id
        )
    ):
        raise BranchMergeError(
            "INVALID_BRANCH_BOUNDARY",
            "The branch conversation state is invalid.",
            http_status=409,
            refresh_preview=True,
        )

    turns = _build_canonical_branch_turns(
        branch_message_id,
        branch_source_message,
        branch_only_messages,
        already_merged_message_ids,
    )
    preview_token = (
        _build_branch_merge_preview_token(
            version=(
                BRANCH_MERGE_PREVIEW_VERSION
            ),
            branch_chat_id=branch_chat_id,
            branch_chat_title=chat_row[
                "branch_chat_title"
            ],
            parent_chat_id=(
                resolved_parent_chat_id
            ),
            parent_chat_title=chat_row[
                "parent_chat_title"
            ],
            branched_from_message_id=(
                parent_message_id
            ),
            branch_message_id=(
                branch_message_id
            ),
            parent_source_message=(
                parent_source_message
            ),
            branch_source_message=(
                branch_source_message
            ),
            parent_only_messages=(
                parent_only_messages
            ),
            branch_only_messages=(
                branch_only_messages
            ),
            expected_parent_last_message_id=(
                parent_last_message_id
            ),
            expected_branch_last_message_id=(
                branch_last_message_id
            ),
            already_merged_source_message_ids=(
                already_merged_message_ids
            ),
            turns=turns,
        )
    )

    return {
        "branch_chat_id": branch_chat_id,
        "parent_chat_id": (
            resolved_parent_chat_id
        ),
        "branched_from_message_id": (
            parent_message_id
        ),
        "branch_message_id": (
            branch_message_id
        ),
        "parent_last_message_id": (
            parent_last_message_id
        ),
        "branch_last_message_id": (
            branch_last_message_id
        ),
        "branch_only_messages": (
            branch_only_messages
        ),
        "turns": turns,
        "preview_token": preview_token,
        "already_merged_operation_by_message": (
            already_merged_operation_by_message
        ),
    }


def _build_branch_merge_request_fingerprint(
    branch_chat_id,
    request,
):
    expected = request.expected
    payload = {
        "branch_chat_id": branch_chat_id,
        "preview_token": request.preview_token,
        "expected": {
            "parent_chat_id": (
                expected.parent_chat_id
            ),
            "branched_from_message_id": (
                expected.branched_from_message_id
            ),
            "branch_message_id": (
                expected.branch_message_id
            ),
            "parent_last_message_id": (
                expected.parent_last_message_id
            ),
            "branch_last_message_id": (
                expected.branch_last_message_id
            ),
        },
        "selected_turns": [
            {
                "turn_key": turn.turn_key,
                "message_ids": list(
                    turn.message_ids
                ),
            }
            for turn in request.selected_turns
        ],
    }

    return _canonical_sha256(payload)


def _load_operation_by_key(
    cursor,
    idempotency_key,
):
    cursor.execute(
        """
        SELECT
            id,
            idempotency_key,
            request_fingerprint,
            branch_chat_id,
            parent_chat_id,
            status,
            inserted_turn_count,
            inserted_message_count,
            first_created_parent_message_id,
            last_created_parent_message_id,
            completed_at
        FROM branch_merge_operations
        WHERE idempotency_key = ?
        """,
        (idempotency_key,),
    )
    return cursor.fetchone()


def _response_from_completed_operation(
    cursor,
    operation_row,
    *,
    replayed,
):
    operation_id = operation_row["id"]
    cursor.execute(
        """
        SELECT
            turn_key,
            turn_position,
            message_position,
            source_branch_message_id,
            created_parent_message_id
        FROM branch_merge_message_mappings
        WHERE merge_operation_id = ?
        ORDER BY
            turn_position ASC,
            message_position ASC,
            id ASC
        """,
        (operation_id,),
    )
    mapping_rows = cursor.fetchall()
    turns = []
    current_turn_position = None

    for mapping_row in mapping_rows:
        turn_position = mapping_row[
            "turn_position"
        ]

        if turn_position != current_turn_position:
            turns.append(
                {
                    "turn_key": mapping_row[
                        "turn_key"
                    ],
                    "source_branch_message_ids": [],
                    "created_parent_message_ids": [],
                }
            )
            current_turn_position = turn_position

        turns[-1][
            "source_branch_message_ids"
        ].append(
            mapping_row[
                "source_branch_message_id"
            ]
        )
        turns[-1][
            "created_parent_message_ids"
        ].append(
            mapping_row[
                "created_parent_message_id"
            ]
        )

    if (
        operation_row["status"]
        != "completed"
        or operation_row["completed_at"]
        is None
        or len(turns)
        != operation_row[
            "inserted_turn_count"
        ]
        or len(mapping_rows)
        != operation_row[
            "inserted_message_count"
        ]
    ):
        raise BranchMergeError(
            "MERGE_FAILED",
            "Stored merge audit data is incomplete.",
            http_status=500,
            operation_id=operation_id,
        )

    return BranchMergeResponse(
        status="completed",
        replayed=replayed,
        operation_id=operation_id,
        idempotency_key=operation_row[
            "idempotency_key"
        ],
        branch_chat_id=operation_row[
            "branch_chat_id"
        ],
        parent_chat_id=operation_row[
            "parent_chat_id"
        ],
        inserted_turn_count=operation_row[
            "inserted_turn_count"
        ],
        inserted_message_count=operation_row[
            "inserted_message_count"
        ],
        first_created_parent_message_id=(
            operation_row[
                "first_created_parent_message_id"
            ]
        ),
        last_created_parent_message_id=(
            operation_row[
                "last_created_parent_message_id"
            ]
        ),
        completed_at=operation_row[
            "completed_at"
        ],
        turns=turns,
    )


def _validate_selection_structure(request):
    if not request.selected_turns:
        raise BranchMergeError(
            "EMPTY_SELECTION",
            "Select at least one complete conversation turn.",
            http_status=422,
        )

    seen_turn_keys = set()
    seen_message_ids = set()
    selected_message_ids = []

    for selected_turn in request.selected_turns:
        if selected_turn.turn_key in seen_turn_keys:
            raise BranchMergeError(
                "INVALID_SELECTED_TURN",
                "A selected turn key appears more than once.",
                http_status=422,
            )

        seen_turn_keys.add(
            selected_turn.turn_key
        )

        if not selected_turn.message_ids:
            raise BranchMergeError(
                "INVALID_SELECTED_TURN",
                "A selected turn has no messages.",
                http_status=422,
            )

        for message_id in selected_turn.message_ids:
            if not _is_positive_integer(
                message_id
            ):
                raise BranchMergeError(
                    "INVALID_SELECTED_TURN",
                    "A selected message ID is invalid.",
                    http_status=422,
                )

            if message_id in seen_message_ids:
                raise BranchMergeError(
                    "DUPLICATE_SELECTED_ID",
                    "A selected message ID appears more than once.",
                    http_status=422,
                )

            seen_message_ids.add(message_id)
            selected_message_ids.append(
                message_id
            )

    return selected_message_ids


def _load_message_owners(
    cursor,
    message_ids,
):
    owners = {}
    chunk_size = 500

    for offset in range(
        0,
        len(message_ids),
        chunk_size,
    ):
        chunk = message_ids[
            offset:offset + chunk_size
        ]
        placeholders = ", ".join(
            "?"
            for _ in chunk
        )
        cursor.execute(
            f"""
            SELECT id, chat_id
            FROM messages
            WHERE id IN ({placeholders})
            """,
            chunk,
        )

        for row in cursor.fetchall():
            owners[row["id"]] = row["chat_id"]

    return owners


def _validate_selected_message_ownership(
    cursor,
    snapshot,
    selected_message_ids,
):
    owners = _load_message_owners(
        cursor,
        selected_message_ids,
    )

    for message_id in selected_message_ids:
        if message_id <= snapshot[
            "branch_message_id"
        ]:
            raise BranchMergeError(
                "MESSAGE_OUTSIDE_BRANCH_CONTINUATION",
                "A selected message is outside the branch continuation.",
                http_status=422,
            )

        if owners.get(message_id) != snapshot[
            "branch_chat_id"
        ]:
            raise BranchMergeError(
                "MESSAGE_NOT_OWNED_BY_BRANCH",
                "A selected message does not belong to this branch.",
                http_status=422,
            )


def _validate_expected_state(
    snapshot,
    request,
):
    expected = request.expected
    actual_values = (
        snapshot["parent_chat_id"],
        snapshot["branched_from_message_id"],
        snapshot["branch_message_id"],
        snapshot["parent_last_message_id"],
        snapshot["branch_last_message_id"],
        snapshot["preview_token"],
    )
    expected_values = (
        expected.parent_chat_id,
        expected.branched_from_message_id,
        expected.branch_message_id,
        expected.parent_last_message_id,
        expected.branch_last_message_id,
        request.preview_token,
    )

    if actual_values != expected_values:
        raise BranchMergeError(
            "STALE_PREVIEW",
            "The branch or parent changed. Refresh the merge preview.",
            http_status=409,
            refresh_preview=True,
        )


def _raise_if_already_merged(
    snapshot,
    selected_message_ids,
):
    operation_by_message = snapshot[
        "already_merged_operation_by_message"
    ]

    for message_id in selected_message_ids:
        operation_id = operation_by_message.get(
            message_id
        )

        if operation_id is not None:
            raise BranchMergeError(
                "MERGE_ALREADY_COMPLETED",
                "A selected branch message was already merged into this parent.",
                http_status=409,
                refresh_preview=True,
                operation_id=operation_id,
            )


def _canonicalize_selected_turns(
    snapshot,
    request,
):
    canonical_turns_by_key = {
        turn["turn_key"]: turn
        for turn in snapshot["turns"]
    }
    selected_turns = []

    for submitted_turn in request.selected_turns:
        canonical_turn = (
            canonical_turns_by_key.get(
                submitted_turn.turn_key
            )
        )

        if canonical_turn is None:
            raise BranchMergeError(
                "INVALID_SELECTED_TURN",
                "A selected turn does not exist in the current branch preview.",
                http_status=422,
            )

        if not canonical_turn["selectable"]:
            reason = canonical_turn["reason"]

            if reason == "already_merged":
                operation_id = None

                for message_id in canonical_turn[
                    "message_ids"
                ]:
                    operation_id = snapshot[
                        "already_merged_operation_by_message"
                    ].get(message_id)

                    if operation_id is not None:
                        break

                raise BranchMergeError(
                    "MERGE_ALREADY_COMPLETED",
                    "A selected branch message was already merged into this parent.",
                    http_status=409,
                    refresh_preview=True,
                    operation_id=operation_id,
                )

            if reason in {
                "orphan_messages",
                "unknown_role",
            }:
                raise BranchMergeError(
                    "ORPHAN_SELECTED_MESSAGE",
                    "The selection contains messages without a safe user anchor.",
                    http_status=422,
                )

            raise BranchMergeError(
                "INVALID_SELECTED_TURN",
                "The selected turn is not eligible for merge execution.",
                http_status=422,
            )

        if list(submitted_turn.message_ids) != list(
            canonical_turn["message_ids"]
        ):
            raise BranchMergeError(
                "INVALID_SELECTED_TURN",
                "Submitted messages do not exactly match the canonical turn.",
                http_status=422,
            )

        selected_turns.append(
            canonical_turn
        )

    selected_turns.sort(
        key=lambda turn: min(
            turn["message_ids"]
        )
    )
    return selected_turns


def _insert_parent_message(
    cursor,
    parent_chat_id,
    source_message,
    merge_created_at,
):
    cursor.execute(
        """
        INSERT INTO messages (
            chat_id,
            role,
            content,
            created_at,
            sources_json,
            model_id,
            attachment_json
        )
        VALUES (?, ?, ?, ?, '[]', NULL, NULL)
        """,
        (
            parent_chat_id,
            source_message["role"],
            source_message["content"],
            merge_created_at,
        ),
    )
    return cursor.lastrowid


def _is_busy_error(error):
    return is_database_busy_error(error)


def execute_branch_merge(
    db_path,
    branch_chat_id,
    request: BranchMergeRequest,
):
    """Execute one internal, idempotent branch-to-parent append transaction."""
    if not isinstance(
        request,
        BranchMergeRequest,
    ):
        request = BranchMergeRequest.model_validate(
            request
        )

    if not _is_positive_integer(
        branch_chat_id
    ):
        raise BranchMergeError(
            "BRANCH_NOT_FOUND",
            "The requested branch chat was not found.",
            http_status=404,
        )

    connection = None

    try:
        connection = get_connection(db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        configure_busy_timeout(connection, 5000)
        begin_write_transaction(connection)
        acquire_branch_merge_lock(connection)

        request_fingerprint = (
            _build_branch_merge_request_fingerprint(
                branch_chat_id,
                request,
            )
        )
        existing_operation = (
            _load_operation_by_key(
                cursor,
                request.idempotency_key,
            )
        )

        if existing_operation is not None:
            if existing_operation[
                "request_fingerprint"
            ] != request_fingerprint:
                raise BranchMergeError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "This idempotency key was already used for a different request.",
                    http_status=409,
                    operation_id=(
                        existing_operation["id"]
                    ),
                )

            if existing_operation["status"] == (
                "completed"
            ):
                response = (
                    _response_from_completed_operation(
                        cursor,
                        existing_operation,
                        replayed=True,
                    )
                )
                connection.commit()
                return response

            raise BranchMergeError(
                "MERGE_BUSY",
                "An identical merge operation is still pending.",
                http_status=503,
                retryable=True,
                operation_id=(
                    existing_operation["id"]
                ),
            )

        selected_message_ids = (
            _validate_selection_structure(
                request
            )
        )
        snapshot = (
            _load_authoritative_merge_snapshot(
                cursor,
                branch_chat_id,
                request.expected,
            )
        )
        _validate_selected_message_ownership(
            cursor,
            snapshot,
            selected_message_ids,
        )
        _raise_if_already_merged(
            snapshot,
            selected_message_ids,
        )
        _validate_expected_state(
            snapshot,
            request,
        )
        selected_turns = (
            _canonicalize_selected_turns(
                snapshot,
                request,
            )
        )

        branch_messages_by_id = {
            message["id"]: message
            for message in snapshot[
                "branch_only_messages"
            ]
        }
        merge_created_at = (
            datetime.now().isoformat()
        )
        cursor.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                request.idempotency_key,
                request_fingerprint,
                request.preview_token,
                branch_chat_id,
                snapshot["parent_chat_id"],
                snapshot[
                    "branched_from_message_id"
                ],
                snapshot["branch_message_id"],
                snapshot[
                    "parent_last_message_id"
                ],
                snapshot[
                    "branch_last_message_id"
                ],
                merge_created_at,
            ),
        )
        operation_id = cursor.lastrowid
        turn_results = []
        created_parent_message_ids = []

        for turn_position, turn in enumerate(
            selected_turns
        ):
            source_ids = list(
                turn["message_ids"]
            )
            created_ids = []

            for message_position, source_id in enumerate(
                source_ids
            ):
                source_message = (
                    branch_messages_by_id[
                        source_id
                    ]
                )
                created_message_id = (
                    _insert_parent_message(
                        cursor,
                        snapshot["parent_chat_id"],
                        source_message,
                        merge_created_at,
                    )
                )
                created_message_fingerprint = (
                    _canonical_sha256(
                        {
                            "role": source_message[
                                "role"
                            ],
                            "content": source_message[
                                "content"
                            ],
                            "created_at": (
                                merge_created_at
                            ),
                        }
                    )
                )

                try:
                    cursor.execute(
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
                            branch_chat_id,
                            snapshot[
                                "parent_chat_id"
                            ],
                            turn["turn_key"],
                            turn_position,
                            message_position,
                            source_id,
                            created_message_id,
                            created_message_fingerprint,
                        ),
                    )
                except DATABASE_INTEGRITY_ERRORS:
                    cursor.execute(
                        """
                        SELECT merge_operation_id
                        FROM branch_merge_message_mappings
                        WHERE branch_chat_id = ?
                          AND parent_chat_id = ?
                          AND source_branch_message_id = ?
                        """,
                        (
                            branch_chat_id,
                            snapshot[
                                "parent_chat_id"
                            ],
                            source_id,
                        ),
                    )
                    mapping_row = cursor.fetchone()

                    if mapping_row is not None:
                        raise BranchMergeError(
                            "MERGE_ALREADY_COMPLETED",
                            "A selected branch message was already merged into this parent.",
                            http_status=409,
                            refresh_preview=True,
                            operation_id=(
                                mapping_row[
                                    "merge_operation_id"
                                ]
                            ),
                        )

                    raise

                created_ids.append(
                    created_message_id
                )
                created_parent_message_ids.append(
                    created_message_id
                )

            turn_results.append(
                BranchMergeTurnResult(
                    turn_key=turn["turn_key"],
                    source_branch_message_ids=(
                        source_ids
                    ),
                    created_parent_message_ids=(
                        created_ids
                    ),
                )
            )

        completed_at = datetime.now().isoformat()
        inserted_turn_count = len(
            turn_results
        )
        inserted_message_count = len(
            created_parent_message_ids
        )
        first_created_message_id = (
            created_parent_message_ids[0]
        )
        last_created_message_id = (
            created_parent_message_ids[-1]
        )
        cursor.execute(
            """
            UPDATE branch_merge_operations
            SET
                status = 'completed',
                inserted_turn_count = ?,
                inserted_message_count = ?,
                first_created_parent_message_id = ?,
                last_created_parent_message_id = ?,
                completed_at = ?
            WHERE id = ?
              AND status = 'pending'
            """,
            (
                inserted_turn_count,
                inserted_message_count,
                first_created_message_id,
                last_created_message_id,
                completed_at,
                operation_id,
            ),
        )

        if cursor.rowcount != 1:
            raise BranchMergeError(
                "MERGE_FAILED",
                "The merge audit operation could not be completed.",
                http_status=500,
                operation_id=operation_id,
            )

        response = BranchMergeResponse(
            status="completed",
            replayed=False,
            operation_id=operation_id,
            idempotency_key=(
                request.idempotency_key
            ),
            branch_chat_id=branch_chat_id,
            parent_chat_id=snapshot[
                "parent_chat_id"
            ],
            inserted_turn_count=(
                inserted_turn_count
            ),
            inserted_message_count=(
                inserted_message_count
            ),
            first_created_parent_message_id=(
                first_created_message_id
            ),
            last_created_parent_message_id=(
                last_created_message_id
            ),
            completed_at=completed_at,
            turns=turn_results,
        )
        connection.commit()
        return response

    except BranchMergeError:
        if (
            connection is not None
            and connection.in_transaction
        ):
            connection.rollback()
        raise

    except DATABASE_OPERATIONAL_ERRORS as error:
        if (
            connection is not None
            and connection.in_transaction
        ):
            connection.rollback()

        if _is_busy_error(error):
            raise BranchMergeError(
                "MERGE_BUSY",
                "The database is busy. Retry the merge shortly.",
                http_status=503,
                retryable=True,
            ) from error

        raise BranchMergeError(
            "MERGE_FAILED",
            "The branch merge could not be completed.",
            http_status=500,
        ) from error

    except Exception as error:
        if (
            connection is not None
            and connection.in_transaction
        ):
            connection.rollback()

        raise BranchMergeError(
            "MERGE_FAILED",
            "The branch merge could not be completed.",
            http_status=500,
        ) from error

    finally:
        if connection is not None:
            connection.close()
