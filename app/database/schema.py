"""Cross-database SQLAlchemy Core schema for Onkar-AI chat persistence.

The column types intentionally preserve current API and SQLite semantics:

- Numeric integer IDs
- ISO-8601 timestamps stored as text
- Boolean-like values stored as 0/1 integers
- JSON payloads stored as text
- Merge audit tables remain free of foreign keys so audit records can
  survive chat deletion

This module does not migrate existing databases automatically.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.engine import Engine


SCHEMA_VERSION = 3

metadata = MetaData()


schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column(
        "version",
        Integer,
        primary_key=True,
        autoincrement=False,
    ),
    Column("description", Text, nullable=False),
    Column("applied_at", Text, nullable=False),
)


folders = Table(
    "folders",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    sqlite_autoincrement=True,
)

Index(
    "uq_folders_name_ci",
    func.lower(folders.c.name),
    unique=True,
)


chats = Table(
    "chats",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("title", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column(
        "is_pinned",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column("folder_id", Integer, nullable=True),
    Column("parent_chat_id", Integer, nullable=True),
    Column(
        "branched_from_message_id",
        Integer,
        nullable=True,
    ),
    Column("branch_message_id", Integer, nullable=True),
    sqlite_autoincrement=True,
)

Index(
    "idx_chats_folder_id",
    chats.c.folder_id,
)
Index(
    "idx_chats_title",
    func.lower(chats.c.title),
)
Index(
    "idx_chats_parent_chat_id",
    chats.c.parent_chat_id,
)
Index(
    "idx_chats_branched_message_id",
    chats.c.branched_from_message_id,
)


messages = Table(
    "messages",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("chat_id", Integer, nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column(
        "sources_json",
        Text,
        nullable=False,
        server_default=text("'[]'"),
    ),
    Column("model_id", Text, nullable=True),
    Column("attachment_json", Text, nullable=True),
    sqlite_autoincrement=True,
)

Index(
    "idx_messages_chat_id",
    messages.c.chat_id,
)
Index(
    "idx_messages_role",
    messages.c.role,
)
Index(
    "idx_messages_created_at",
    messages.c.created_at,
)


message_bookmarks = Table(
    "message_bookmarks",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("chat_id", Integer, nullable=False),
    Column("message_id", Integer, nullable=False),
    Column(
        "note",
        Text,
        nullable=False,
        server_default=text("''"),
    ),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint(
        "message_id",
        name="uq_message_bookmarks_message_id",
    ),
    sqlite_autoincrement=True,
)

Index(
    "idx_message_bookmarks_chat_id",
    message_bookmarks.c.chat_id,
)
Index(
    "idx_message_bookmarks_created_at",
    message_bookmarks.c.created_at,
)


documents = Table(
    "documents",
    metadata,
    Column(
        "document_id",
        Text,
        primary_key=True,
    ),
    Column("chat_id", Integer, nullable=False),
    Column("filename", Text, nullable=False),
    Column("file_path", Text, nullable=False),
    Column("file_hash", Text, nullable=False),
    Column(
        "file_size",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "page_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "chunk_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "status",
        Text,
        nullable=False,
        server_default=text("'processing'"),
    ),
    Column(
        "is_selected",
        Integer,
        nullable=False,
        server_default=text("1"),
    ),
    Column("uploaded_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

Index(
    "uq_documents_chat_filename_ci",
    documents.c.chat_id,
    func.lower(documents.c.filename),
    unique=True,
)
Index(
    "idx_documents_chat_id",
    documents.c.chat_id,
)
Index(
    "idx_documents_selected",
    documents.c.chat_id,
    documents.c.is_selected,
)
Index(
    "idx_documents_hash",
    documents.c.chat_id,
    documents.c.file_hash,
)


branch_merge_operations = Table(
    "branch_merge_operations",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("idempotency_key", Text, nullable=False),
    Column("request_fingerprint", Text, nullable=False),
    Column("preview_token", Text, nullable=False),
    Column("branch_chat_id", Integer, nullable=False),
    Column("parent_chat_id", Integer, nullable=False),
    Column(
        "branched_from_message_id",
        Integer,
        nullable=False,
    ),
    Column("branch_message_id", Integer, nullable=False),
    Column(
        "expected_parent_last_message_id",
        Integer,
        nullable=False,
    ),
    Column(
        "expected_branch_last_message_id",
        Integer,
        nullable=False,
    ),
    Column("status", Text, nullable=False),
    Column(
        "inserted_turn_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "inserted_message_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "first_created_parent_message_id",
        Integer,
        nullable=True,
    ),
    Column(
        "last_created_parent_message_id",
        Integer,
        nullable=True,
    ),
    Column("created_at", Text, nullable=False),
    Column("completed_at", Text, nullable=True),
    UniqueConstraint(
        "idempotency_key",
        name="uq_branch_merge_operations_idempotency_key",
    ),
    CheckConstraint(
        "status IN ('pending', 'completed')",
        name="ck_branch_merge_operations_status",
    ),
    sqlite_autoincrement=True,
)

Index(
    "idx_branch_merge_operations_branch",
    branch_merge_operations.c.branch_chat_id,
    branch_merge_operations.c.completed_at,
)
Index(
    "idx_branch_merge_operations_parent",
    branch_merge_operations.c.parent_chat_id,
    branch_merge_operations.c.completed_at,
)


branch_merge_message_mappings = Table(
    "branch_merge_message_mappings",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        autoincrement=True,
    ),
    Column("merge_operation_id", Integer, nullable=False),
    Column("branch_chat_id", Integer, nullable=False),
    Column("parent_chat_id", Integer, nullable=False),
    Column("turn_key", Text, nullable=False),
    Column("turn_position", Integer, nullable=False),
    Column("message_position", Integer, nullable=False),
    Column(
        "source_branch_message_id",
        Integer,
        nullable=False,
    ),
    Column(
        "created_parent_message_id",
        Integer,
        nullable=False,
    ),
    Column(
        "created_message_fingerprint",
        Text,
        nullable=False,
    ),
    UniqueConstraint(
        "created_parent_message_id",
        name=(
            "uq_branch_merge_mappings_"
            "created_parent_message_id"
        ),
    ),
    UniqueConstraint(
        "merge_operation_id",
        "source_branch_message_id",
        name=(
            "uq_branch_merge_mappings_"
            "operation_source"
        ),
    ),
    UniqueConstraint(
        "branch_chat_id",
        "parent_chat_id",
        "source_branch_message_id",
        name=(
            "uq_branch_merge_mappings_"
            "branch_parent_source"
        ),
    ),
    sqlite_autoincrement=True,
)

Index(
    "idx_branch_merge_mappings_operation",
    branch_merge_message_mappings.c.merge_operation_id,
)
Index(
    "idx_branch_merge_mappings_chats",
    branch_merge_message_mappings.c.branch_chat_id,
    branch_merge_message_mappings.c.parent_chat_id,
)


document_recovery_runs = Table(
    "document_recovery_runs",
    metadata,
    Column(
        "run_id",
        Text,
        primary_key=True,
    ),
    Column(
        "status",
        Text,
        nullable=False,
    ),
    Column(
        "recovery_enabled",
        Integer,
        nullable=False,
    ),
    Column(
        "started_at",
        Text,
        nullable=False,
    ),
    Column(
        "finished_at",
        Text,
        nullable=False,
    ),
    Column(
        "duration_ms",
        Integer,
        nullable=False,
    ),
    Column(
        "total_examined",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "candidate_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "processing_recovered_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "deleting_completed_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "failure_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "skipped_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "recent_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "invalid_timestamp_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "deferred_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    CheckConstraint(
        (
            "status IN ("
            "'disabled', "
            "'completed', "
            "'completed_with_failures', "
            "'skipped_lock_held', "
            "'failed'"
            ")"
        ),
        name=(
            "ck_document_recovery_runs_status"
        ),
    ),
    CheckConstraint(
        "recovery_enabled IN (0, 1)",
        name=(
            "ck_document_recovery_runs_enabled"
        ),
    ),
    CheckConstraint(
        (
            "duration_ms >= 0 "
            "AND total_examined >= 0 "
            "AND candidate_count >= 0 "
            "AND processing_recovered_count >= 0 "
            "AND deleting_completed_count >= 0 "
            "AND failure_count >= 0 "
            "AND skipped_count >= 0 "
            "AND recent_count >= 0 "
            "AND invalid_timestamp_count >= 0 "
            "AND deferred_count >= 0"
        ),
        name=(
            "ck_document_recovery_runs_nonnegative"
        ),
    ),
)


system_incidents = Table(
    "system_incidents",
    metadata,
    Column(
        "incident_id",
        Text,
        primary_key=True,
    ),
    Column(
        "incident_key",
        Text,
        nullable=False,
    ),
    Column(
        "component",
        Text,
        nullable=False,
    ),
    Column(
        "severity",
        Text,
        nullable=False,
    ),
    Column(
        "source_status",
        Text,
        nullable=False,
    ),
    Column(
        "detail",
        Text,
        nullable=False,
    ),
    Column(
        "critical",
        Integer,
        nullable=False,
    ),
    Column(
        "state",
        Text,
        nullable=False,
    ),
    Column(
        "fingerprint",
        Text,
        nullable=False,
    ),
    Column(
        "opened_at",
        Text,
        nullable=False,
    ),
    Column(
        "last_seen_at",
        Text,
        nullable=False,
    ),
    Column(
        "resolved_at",
        Text,
        nullable=True,
    ),
    Column(
        "occurrence_count",
        Integer,
        nullable=False,
        server_default=text("1"),
    ),
    CheckConstraint(
        (
            "severity IN ("
            "'warning', "
            "'critical'"
            ")"
        ),
        name="ck_system_incidents_severity",
    ),
    CheckConstraint(
        (
            "source_status IN ("
            "'degraded', "
            "'unavailable'"
            ")"
        ),
        name=(
            "ck_system_incidents_source_status"
        ),
    ),
    CheckConstraint(
        (
            "state IN ("
            "'open', "
            "'resolved'"
            ")"
        ),
        name="ck_system_incidents_state",
    ),
    CheckConstraint(
        "critical IN (0, 1)",
        name="ck_system_incidents_critical",
    ),
    CheckConstraint(
        "occurrence_count >= 1",
        name=(
            "ck_system_incidents_occurrence_count"
        ),
    ),
    CheckConstraint(
        "length(incident_id) BETWEEN 1 AND 128",
        name="ck_system_incidents_id_length",
    ),
    CheckConstraint(
        "length(incident_key) BETWEEN 1 AND 128",
        name="ck_system_incidents_key_length",
    ),
    CheckConstraint(
        "length(component) BETWEEN 1 AND 64",
        name=(
            "ck_system_incidents_component_length"
        ),
    ),
    CheckConstraint(
        "length(detail) BETWEEN 1 AND 96",
        name=(
            "ck_system_incidents_detail_length"
        ),
    ),
    CheckConstraint(
        "length(fingerprint) = 64",
        name=(
            "ck_system_incidents_fingerprint_length"
        ),
    ),
    CheckConstraint(
        (
            "("
            "state = 'open' "
            "AND resolved_at IS NULL"
            ") OR ("
            "state = 'resolved' "
            "AND resolved_at IS NOT NULL"
            ")"
        ),
        name=(
            "ck_system_incidents_resolution_state"
        ),
    ),
    Index(
        "ix_system_incidents_key_state",
        "incident_key",
        "state",
    ),
    Index(
        "ix_system_incidents_state_last_seen",
        "state",
        "last_seen_at",
    ),
)


EXPECTED_TABLE_NAMES = frozenset(
    {
        "schema_migrations",
        "folders",
        "chats",
        "messages",
        "message_bookmarks",
        "documents",
        "document_recovery_runs",
        "system_incidents",
        "branch_merge_operations",
        "branch_merge_message_mappings",
    }
)


def create_schema(engine: Engine) -> None:
    """Create missing tables and indexes without deleting existing data."""
    metadata.create_all(
        bind=engine,
        checkfirst=True,
    )
