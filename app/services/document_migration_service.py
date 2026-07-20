from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.document_object_service import (
    build_document_object_key,
)
from app.services.document_service import (
    calculate_file_hash,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
    normalize_object_key,
)


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


class DocumentMigrationError(RuntimeError):
    """Raised when a document migration cannot complete safely."""


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    chat_id: int
    filename: str
    current_reference: str
    file_hash: str
    file_size: int
    status: str


@dataclass(frozen=True)
class DocumentMigrationItem:
    record: DocumentRecord
    source_path: Path
    target_key: str
    file_hash: str
    file_size: int
    target_preexisting: bool


@dataclass(frozen=True)
class DocumentMigrationIssue:
    record: DocumentRecord
    reason: str
    attempted_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentMigrationPlan:
    ready: tuple[DocumentMigrationItem, ...]
    already_migrated: tuple[DocumentRecord, ...]
    missing: tuple[DocumentMigrationIssue, ...]
    invalid: tuple[DocumentMigrationIssue, ...]
    skipped_status: tuple[DocumentRecord, ...]

    @property
    def total_rows(self) -> int:
        return (
            len(self.ready)
            + len(self.already_migrated)
            + len(self.missing)
            + len(self.invalid)
            + len(self.skipped_status)
        )

    @property
    def can_execute(self) -> bool:
        return (
            not self.missing
            and not self.invalid
        )


@dataclass(frozen=True)
class DocumentMigrationReport:
    migrated: int
    already_migrated: int
    created_objects: int


def _safe_filename(
    filename: object,
) -> str:
    candidate = str(
        filename or ""
    ).strip()

    if (
        not candidate
        or "/" in candidate
        or "\\" in candidate
        or Path(candidate).suffix.lower()
        != ".pdf"
        or len(candidate) > 255
        or any(
            ord(character) < 32
            or ord(character) == 127
            for character in candidate
        )
    ):
        raise DocumentMigrationError(
            "Invalid PDF filename."
        )

    return candidate


def _to_record(
    row: Any,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=str(row[0]),
        chat_id=int(row[1]),
        filename=_safe_filename(row[2]),
        current_reference=str(
            row[3] or ""
        ).strip(),
        file_hash=str(
            row[4] or ""
        ).strip().casefold(),
        file_size=int(
            row[5] or 0
        ),
        status=str(
            row[6] or ""
        ).strip().casefold(),
    )


def _load_document_records(
    connection,
) -> list[DocumentRecord]:
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                document_id,
                chat_id,
                filename,
                file_path,
                file_hash,
                file_size,
                status
            FROM documents
            ORDER BY chat_id, filename
            """
        )

        return [
            _to_record(row)
            for row in cursor.fetchall()
        ]

    finally:
        close = getattr(
            cursor,
            "close",
            None,
        )

        if callable(close):
            close()


def _canonical_object_key(
    reference: str,
) -> str | None:
    if not reference.startswith(
        "chats/"
    ):
        return None

    try:
        return normalize_object_key(
            reference
        )
    except ValueError:
        return None


def _candidate_source_paths(
    record: DocumentRecord,
    source_roots: Iterable[
        str | Path
    ],
) -> tuple[Path, ...]:
    candidates: list[Path] = []

    if (
        record.current_reference
        and _canonical_object_key(
            record.current_reference
        )
        is None
    ):
        stored_path = Path(
            record.current_reference
        ).expanduser()

        if not stored_path.is_absolute():
            stored_path = (
                Path.cwd()
                / stored_path
            )

        candidates.append(
            stored_path.resolve(
                strict=False
            )
        )

    for root_value in source_roots:
        root = Path(
            root_value
        ).expanduser().resolve(
            strict=False
        )

        chat_directory_name = (
            f"chat_{record.chat_id}"
        )

        candidates.append(
            (
                root
                / chat_directory_name
                / record.filename
            ).resolve(strict=False)
        )

        if (
            root.name
            == chat_directory_name
        ):
            candidates.append(
                (
                    root
                    / record.filename
                ).resolve(
                    strict=False
                )
            )

    unique_candidates: list[Path] = []
    seen: set[str] = set()

    for candidate in candidates:
        marker = str(
            candidate
        ).casefold()

        if marker in seen:
            continue

        seen.add(marker)
        unique_candidates.append(
            candidate
        )

    return tuple(
        unique_candidates
    )


def _read_pdf_file(
    path: Path,
) -> tuple[bytes, str, int]:
    try:
        content = path.read_bytes()
    except FileNotFoundError as error:
        raise DocumentNotFoundError(
            "Legacy PDF was not found."
        ) from error
    except OSError as error:
        raise DocumentMigrationError(
            "Legacy PDF could not be read."
        ) from error

    if (
        not content
        or not content.startswith(
            b"%PDF-"
        )
    ):
        raise DocumentMigrationError(
            "Legacy file is not a valid PDF."
        )

    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentMigrationError(
            "Legacy PDF exceeds the 25 MB limit."
        )

    return (
        content,
        calculate_file_hash(
            content
        ),
        len(content),
    )


def _validate_metadata(
    record: DocumentRecord,
    *,
    actual_hash: str,
    actual_size: int,
) -> None:
    if (
        record.file_hash
        and record.file_hash
        != actual_hash
    ):
        raise DocumentMigrationError(
            "Stored file hash does not match "
            "the legacy PDF."
        )

    if (
        record.file_size > 0
        and record.file_size
        != actual_size
    ):
        raise DocumentMigrationError(
            "Stored file size does not match "
            "the legacy PDF."
        )


def _validate_existing_object(
    *,
    storage,
    key: str,
    expected_hash: str | None = None,
    expected_size: int | None = None,
) -> tuple[str, int]:
    try:
        content = storage.get_bytes(
            key
        )
    except DocumentNotFoundError:
        raise
    except DocumentStorageError:
        raise
    except Exception as error:
        raise DocumentMigrationError(
            "Stored document object could "
            "not be read."
        ) from error

    if (
        not content
        or not content.startswith(
            b"%PDF-"
        )
    ):
        raise DocumentMigrationError(
            "Stored document object is not "
            "a valid PDF."
        )

    actual_hash = calculate_file_hash(
        content
    )

    actual_size = len(content)

    if (
        expected_hash
        and actual_hash
        != expected_hash
    ):
        raise DocumentMigrationError(
            "Stored object hash validation failed."
        )

    if (
        expected_size is not None
        and actual_size
        != expected_size
    ):
        raise DocumentMigrationError(
            "Stored object size validation failed."
        )

    return (
        actual_hash,
        actual_size,
    )


def build_document_migration_plan(
    connection,
    storage,
    *,
    source_roots: Iterable[
        str | Path
    ] = (),
    include_non_ready: bool = False,
) -> DocumentMigrationPlan:
    records = _load_document_records(
        connection
    )

    ready: list[
        DocumentMigrationItem
    ] = []

    already_migrated: list[
        DocumentRecord
    ] = []

    missing: list[
        DocumentMigrationIssue
    ] = []

    invalid: list[
        DocumentMigrationIssue
    ] = []

    skipped_status: list[
        DocumentRecord
    ] = []

    for record in records:
        if (
            not include_non_ready
            and record.status != "ready"
        ):
            skipped_status.append(
                record
            )
            continue

        current_key = (
            _canonical_object_key(
                record.current_reference
            )
        )

        if current_key is not None:
            try:
                if storage.exists(
                    current_key
                ):
                    actual_hash, actual_size = (
                        _validate_existing_object(
                            storage=storage,
                            key=current_key,
                            expected_hash=(
                                record.file_hash
                                or None
                            ),
                            expected_size=(
                                record.file_size
                                if record.file_size > 0
                                else None
                            ),
                        )
                    )

                    del actual_hash
                    del actual_size

                    already_migrated.append(
                        record
                    )
                    continue

            except (
                DocumentMigrationError,
                DocumentStorageError,
            ) as error:
                invalid.append(
                    DocumentMigrationIssue(
                        record=record,
                        reason=str(error),
                    )
                )
                continue

        candidates = (
            _candidate_source_paths(
                record,
                source_roots,
            )
        )

        source_path = next(
            (
                candidate
                for candidate in candidates
                if candidate.is_file()
            ),
            None,
        )

        if source_path is None:
            missing.append(
                DocumentMigrationIssue(
                    record=record,
                    reason=(
                        "No readable legacy PDF "
                        "was found."
                    ),
                    attempted_paths=tuple(
                        str(candidate)
                        for candidate
                        in candidates
                    ),
                )
            )
            continue

        try:
            (
                content,
                actual_hash,
                actual_size,
            ) = _read_pdf_file(
                source_path
            )

            del content

            _validate_metadata(
                record,
                actual_hash=actual_hash,
                actual_size=actual_size,
            )

            target_key = (
                build_document_object_key(
                    chat_id=record.chat_id,
                    document_id=(
                        record.document_id
                    ),
                    filename=record.filename,
                    file_hash=actual_hash,
                )
            )

            target_preexisting = (
                storage.exists(
                    target_key
                )
            )

            if target_preexisting:
                _validate_existing_object(
                    storage=storage,
                    key=target_key,
                    expected_hash=actual_hash,
                    expected_size=actual_size,
                )

            ready.append(
                DocumentMigrationItem(
                    record=record,
                    source_path=source_path,
                    target_key=target_key,
                    file_hash=actual_hash,
                    file_size=actual_size,
                    target_preexisting=(
                        target_preexisting
                    ),
                )
            )

        except (
            DocumentMigrationError,
            DocumentStorageError,
        ) as error:
            invalid.append(
                DocumentMigrationIssue(
                    record=record,
                    reason=str(error),
                    attempted_paths=tuple(
                        str(candidate)
                        for candidate
                        in candidates
                    ),
                )
            )

    return DocumentMigrationPlan(
        ready=tuple(ready),
        already_migrated=tuple(
            already_migrated
        ),
        missing=tuple(missing),
        invalid=tuple(invalid),
        skipped_status=tuple(
            skipped_status
        ),
    )


def execute_document_migration(
    plan: DocumentMigrationPlan,
    connection,
    storage,
) -> DocumentMigrationReport:
    if not plan.can_execute:
        raise DocumentMigrationError(
            "Migration preflight contains "
            "missing or invalid documents."
        )

    created_keys: list[str] = []

    try:
        for item in plan.ready:
            (
                content,
                actual_hash,
                actual_size,
            ) = _read_pdf_file(
                item.source_path
            )

            if (
                actual_hash
                != item.file_hash
                or actual_size
                != item.file_size
            ):
                raise DocumentMigrationError(
                    "A legacy PDF changed after "
                    "the preflight scan."
                )

            if storage.exists(
                item.target_key
            ):
                _validate_existing_object(
                    storage=storage,
                    key=item.target_key,
                    expected_hash=(
                        item.file_hash
                    ),
                    expected_size=(
                        item.file_size
                    ),
                )
            else:
                storage.put_bytes(
                    item.target_key,
                    content,
                    content_type=(
                        "application/pdf"
                    ),
                )

                created_keys.append(
                    item.target_key
                )

                _validate_existing_object(
                    storage=storage,
                    key=item.target_key,
                    expected_hash=(
                        item.file_hash
                    ),
                    expected_size=(
                        item.file_size
                    ),
                )

        cursor = connection.cursor()

        try:
            now = datetime.now(
                timezone.utc
            ).isoformat()

            for item in plan.ready:
                cursor.execute(
                    """
                    UPDATE documents
                    SET
                        file_path = ?,
                        file_hash = ?,
                        file_size = ?,
                        updated_at = ?
                    WHERE document_id = ?
                      AND chat_id = ?
                      AND COALESCE(file_path, '') = ?
                    """,
                    (
                        item.target_key,
                        item.file_hash,
                        item.file_size,
                        now,
                        item.record.document_id,
                        item.record.chat_id,
                        item.record.current_reference,
                    ),
                )

                if cursor.rowcount != 1:
                    raise DocumentMigrationError(
                        "A document record changed "
                        "during migration."
                    )

        finally:
            close = getattr(
                cursor,
                "close",
                None,
            )

            if callable(close):
                close()

        connection.commit()

    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass

        cleanup_failed = False

        for key in reversed(
            created_keys
        ):
            try:
                storage.delete(
                    key
                )
            except Exception:
                cleanup_failed = True

        if cleanup_failed:
            raise DocumentMigrationError(
                "Migration failed and newly "
                "created objects could not all "
                "be removed."
            ) from error

        if isinstance(
            error,
            DocumentMigrationError,
        ):
            raise

        raise DocumentMigrationError(
            "Document migration failed."
        ) from error

    return DocumentMigrationReport(
        migrated=len(plan.ready),
        already_migrated=len(
            plan.already_migrated
        ),
        created_objects=len(
            created_keys
        ),
    )
