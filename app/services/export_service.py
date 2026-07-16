import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config.settings import UPLOAD_DIR
from app.models.chat import ChatBackupImportRequest
from app.services.document_service import (
    calculate_file_hash,
    create_document,
    delete_chat_documents,
    list_documents,
    mark_document_ready,
    set_document_selected,
)
from app.services.history_service import (
    delete_chat,
    get_chats,
    get_messages,
    restore_chat_backup,
)
from app.services.rag_service import RAGService


FULL_BACKUP_SCHEMA_VERSION = 1
FULL_BACKUP_TYPE = "full_chat_zip"

MAX_ZIP_SIZE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_SIZE_BYTES = 100 * 1024 * 1024
MAX_MANIFEST_SIZE_BYTES = 2 * 1024 * 1024
MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024
MAX_PDF_COUNT = 50
MAX_COMPRESSION_RATIO = 150

MANIFEST_NAME = "manifest.json"
DOCUMENTS_PREFIX = "documents/"


class BackupValidationError(ValueError):
    """Raised when a ZIP backup is invalid or unsafe."""


class ChatBackupNotFoundError(LookupError):
    """Raised when the requested chat does not exist."""


def _safe_pdf_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise BackupValidationError(
            "A document has an invalid filename."
        )

    safe_filename = Path(filename).name

    if (
        not safe_filename
        or safe_filename != filename
        or Path(safe_filename).suffix.lower() != ".pdf"
    ):
        raise BackupValidationError(
            "A document has an unsafe or unsupported filename."
        )

    return safe_filename


def _safe_download_name(title: str, chat_id: int) -> str:
    cleaned = "".join(
        character
        if character.isalnum()
        or character in {"-", "_", " "}
        else "_"
        for character in title
    )

    cleaned = "_".join(cleaned.split()).strip("_")

    if not cleaned:
        cleaned = f"chat_{chat_id}"

    return f"{cleaned}_full_backup.zip"


def _find_chat(chat_id: int) -> dict[str, Any]:
    if chat_id <= 0:
        raise ChatBackupNotFoundError(
            "Chat not found."
        )

    for chat in get_chats():
        if int(chat.get("id", 0)) == chat_id:
            return chat

    raise ChatBackupNotFoundError(
        "Chat not found."
    )


def _normalise_attachment(
    message: dict[str, Any],
) -> dict[str, Any] | None:
    attachment = message.get("attachment")

    if isinstance(attachment, dict):
        return attachment

    filename = message.get("fileName")
    file_type = message.get("fileType")
    file_size = message.get("fileSize")

    if not filename and not file_type and file_size is None:
        return None

    return {
        "filename": filename,
        "type": file_type,
        "size": file_size,
    }


def _build_backup_messages(
    chat_id: int,
) -> list[dict[str, Any]]:
    messages = get_messages(
        chat_id,
        limit=1000,
    )

    backup_messages = []

    for index, message in enumerate(
        messages,
        start=1,
    ):
        backup_messages.append(
            {
                "index": index,
                "role": message.get("role"),
                "content": message.get(
                    "content",
                    "",
                ),
                "model_id": (
                    message.get("model_id")
                    or message.get("modelId")
                ),
                "created_at": message.get(
                    "created_at"
                ),
                "attachment": _normalise_attachment(
                    message
                ),
                "sources": message.get("sources") or [],
            }
        )

    if not backup_messages:
        backup_messages.append(
            {
                "index": 1,
                "role": "assistant",
                "content": "Hello! How can I help you today?",
                "model_id": None,
                "created_at": None,
                "attachment": None,
                "sources": [],
            }
        )

    return backup_messages


def _resolve_document_path(
    chat_id: int,
    document: dict[str, Any],
) -> Path:
    safe_filename = _safe_pdf_filename(
        str(document.get("filename", ""))
    )

    expected_directory = (
        UPLOAD_DIR / f"chat_{chat_id}"
    ).resolve(strict=False)

    stored_path = Path(
        str(document.get("file_path", ""))
    ).resolve(strict=False)

    expected_path = (
        expected_directory / safe_filename
    ).resolve(strict=False)

    if (
        not stored_path.is_relative_to(expected_directory)
        or stored_path != expected_path
    ):
        raise BackupValidationError(
            f"Unsafe document path detected for {safe_filename}."
        )

    if not stored_path.is_file():
        raise BackupValidationError(
            f"Document file is missing: {safe_filename}."
        )

    return stored_path


def _build_manifest(
    chat: dict[str, Any],
    messages: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    model_ids = [
        message.get("model_id")
        for message in messages
        if message.get("model_id")
    ]

    selected_model_id = model_ids[-1] if model_ids else None

    return {
        "schema_version": FULL_BACKUP_SCHEMA_VERSION,
        "application": "Onkar AI",
        "backup_type": FULL_BACKUP_TYPE,
        "exported_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "chat": {
            "id": chat.get("id"),
            "title": chat.get("title") or "Imported Chat",
            "created_at": chat.get("created_at"),
            "is_pinned": bool(chat.get("is_pinned")),
            "folder_id": chat.get("folder_id"),
            "folder_name": chat.get("folder_name"),
        },
        "model": {
            "selected_id": selected_model_id,
            "selected_name": selected_model_id,
            "default_id": None,
        },
        "messages": messages,
        "documents": documents,
        "warnings": warnings,
    }


def create_full_chat_backup(
    chat_id: int,
) -> tuple[Path, str]:
    chat = _find_chat(chat_id)
    messages = _build_backup_messages(chat_id)

    document_records = list_documents(chat_id)

    archive_documents = []
    files_to_add: list[tuple[Path, str]] = []
    warnings = []
    seen_filenames = set()

    for document in document_records:
        filename = _safe_pdf_filename(
            str(document.get("filename", ""))
        )

        filename_key = filename.casefold()

        if filename_key in seen_filenames:
            raise BackupValidationError(
                "Duplicate document filenames were found."
            )

        seen_filenames.add(filename_key)

        if document.get("status") != "ready":
            warnings.append(
                f"{filename} was skipped because it is not ready."
            )
            continue

        file_path = _resolve_document_path(
            chat_id,
            document,
        )

        file_size = file_path.stat().st_size

        if file_size > MAX_PDF_SIZE_BYTES:
            raise BackupValidationError(
                f"{filename} is larger than the 25 MB per-file limit."
            )

        file_content = file_path.read_bytes()
        file_hash = calculate_file_hash(file_content)

        archive_path = f"{DOCUMENTS_PREFIX}{filename}"

        archive_documents.append(
            {
                "filename": filename,
                "archive_path": archive_path,
                "file_hash": file_hash,
                "file_size": file_size,
                "page_count": int(
                    document.get("page_count", 0) or 0
                ),
                "chunk_count": int(
                    document.get("chunk_count", 0) or 0
                ),
                "is_selected": bool(
                    document.get("is_selected", True)
                ),
            }
        )

        files_to_add.append((file_path, archive_path))

    if len(files_to_add) > MAX_PDF_COUNT:
        raise BackupValidationError(
            f"A maximum of {MAX_PDF_COUNT} PDFs can be backed up at once."
        )

    manifest = _build_manifest(
        chat=chat,
        messages=messages,
        documents=archive_documents,
        warnings=warnings,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix="onkar_ai_backup_",
        suffix=".zip",
    )
    os.close(file_descriptor)

    temporary_path = Path(temporary_name)

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            for file_path, archive_path in files_to_add:
                archive.write(
                    file_path,
                    arcname=archive_path,
                )

        if temporary_path.stat().st_size > MAX_ZIP_SIZE_BYTES:
            raise BackupValidationError(
                "The generated backup is larger than the 50 MB limit."
            )

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    download_name = _safe_download_name(
        str(chat.get("title") or "chat"),
        chat_id,
    )

    return temporary_path, download_name


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def _validate_archive_entry(info: zipfile.ZipInfo) -> None:
    name = info.filename

    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or Path(name).is_absolute()
        or ".." in Path(name).parts
    ):
        raise BackupValidationError(
            "The ZIP contains an unsafe path."
        )

    if info.flag_bits & 0x1:
        raise BackupValidationError(
            "Encrypted ZIP entries are not supported."
        )

    if _is_symlink(info):
        raise BackupValidationError(
            "Symbolic links are not allowed in backups."
        )

    if info.is_dir():
        if name != DOCUMENTS_PREFIX:
            raise BackupValidationError(
                "The ZIP contains an unsupported directory."
            )
        return

    if name == MANIFEST_NAME:
        if info.file_size > MAX_MANIFEST_SIZE_BYTES:
            raise BackupValidationError(
                "The backup manifest is too large."
            )
        return

    if not name.startswith(DOCUMENTS_PREFIX):
        raise BackupValidationError(
            "The ZIP contains an unsupported file."
        )

    relative_name = name[len(DOCUMENTS_PREFIX):]

    if not relative_name or "/" in relative_name:
        raise BackupValidationError(
            "Nested document folders are not allowed."
        )

    _safe_pdf_filename(relative_name)

    if info.file_size > MAX_PDF_SIZE_BYTES:
        raise BackupValidationError(
            f"{relative_name} is larger than the 25 MB per-file limit."
        )

    if (
        info.file_size > 1024 * 1024
        and info.compress_size > 0
        and (info.file_size / info.compress_size)
        > MAX_COMPRESSION_RATIO
    ):
        raise BackupValidationError(
            "The ZIP has an unsafe compression ratio."
        )


def _read_and_validate_manifest(
    archive: zipfile.ZipFile,
    names: set[str],
) -> dict[str, Any]:
    if MANIFEST_NAME not in names:
        raise BackupValidationError(
            "The ZIP does not contain manifest.json."
        )

    try:
        raw_manifest = archive.read(MANIFEST_NAME)
    except KeyError as error:
        raise BackupValidationError(
            "The ZIP manifest could not be read."
        ) from error

    if len(raw_manifest) > MAX_MANIFEST_SIZE_BYTES:
        raise BackupValidationError(
            "The backup manifest is too large."
        )

    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupValidationError(
            "The ZIP contains an invalid manifest."
        ) from error

    if (
        not isinstance(manifest, dict)
        or manifest.get("backup_type") != FULL_BACKUP_TYPE
    ):
        raise BackupValidationError(
            "This is not an Onkar AI full chat backup."
        )

    validation_payload = {
        "schema_version": manifest.get("schema_version"),
        "application": manifest.get("application"),
        "exported_at": manifest.get("exported_at"),
        "chat": manifest.get("chat"),
        "model": manifest.get("model"),
        "messages": manifest.get("messages"),
    }

    try:
        validated = ChatBackupImportRequest.model_validate(
            validation_payload
        )
    except ValidationError as error:
        first_error = error.errors()[0] if error.errors() else {}
        message = first_error.get("msg", "Invalid backup data.")

        raise BackupValidationError(
            f"Invalid chat backup: {message}"
        ) from error

    normalised_manifest = dict(manifest)
    normalised_manifest.update(
        validated.model_dump(mode="json")
    )

    return normalised_manifest


def _read_document_payloads(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
    names: set[str],
) -> list[dict[str, Any]]:
    document_metadata = manifest.get("documents", [])

    if not isinstance(document_metadata, list):
        raise BackupValidationError(
            "The document list in the manifest is invalid."
        )

    if len(document_metadata) > MAX_PDF_COUNT:
        raise BackupValidationError(
            f"A maximum of {MAX_PDF_COUNT} PDFs can be restored at once."
        )

    expected_archive_paths = set()
    seen_filenames = set()
    payloads = []

    for document in document_metadata:
        if not isinstance(document, dict):
            raise BackupValidationError(
                "A document record in the manifest is invalid."
            )

        filename = _safe_pdf_filename(
            str(document.get("filename", ""))
        )

        filename_key = filename.casefold()

        if filename_key in seen_filenames:
            raise BackupValidationError(
                "The manifest contains duplicate PDF filenames."
            )

        seen_filenames.add(filename_key)

        archive_path = document.get("archive_path")
        expected_path = f"{DOCUMENTS_PREFIX}{filename}"

        if archive_path != expected_path:
            raise BackupValidationError(
                f"Invalid archive path for {filename}."
            )

        if archive_path not in names:
            raise BackupValidationError(
                f"The ZIP is missing {filename}."
            )

        expected_archive_paths.add(archive_path)

        file_content = archive.read(archive_path)

        if (
            not file_content
            or not file_content.startswith(b"%PDF-")
        ):
            raise BackupValidationError(
                f"{filename} is not a valid PDF file."
            )

        if len(file_content) > MAX_PDF_SIZE_BYTES:
            raise BackupValidationError(
                f"{filename} is larger than the 25 MB per-file limit."
            )

        expected_hash = str(
            document.get("file_hash", "")
        ).lower()
        actual_hash = hashlib.sha256(file_content).hexdigest()

        if not expected_hash or actual_hash != expected_hash:
            raise BackupValidationError(
                f"Integrity check failed for {filename}."
            )

        expected_size = document.get("file_size")

        try:
            expected_size_value = (
                int(expected_size)
                if expected_size is not None
                else None
            )
        except (TypeError, ValueError) as error:
            raise BackupValidationError(
                f"Invalid file size metadata for {filename}."
            ) from error

        if (
            expected_size_value is not None
            and expected_size_value != len(file_content)
        ):
            raise BackupValidationError(
                f"File size check failed for {filename}."
            )

        payloads.append(
            {
                "filename": filename,
                "content": file_content,
                "file_hash": actual_hash,
                "file_size": len(file_content),
                "is_selected": bool(
                    document.get("is_selected", True)
                ),
            }
        )

    actual_archive_paths = {
        name
        for name in names
        if name.startswith(DOCUMENTS_PREFIX)
        and name != DOCUMENTS_PREFIX
    }

    if actual_archive_paths != expected_archive_paths:
        raise BackupValidationError(
            "The ZIP document list does not match the manifest."
        )

    return payloads


def restore_full_chat_backup(
    archive_content: bytes,
) -> dict[str, Any]:
    if not archive_content:
        raise BackupValidationError(
            "The uploaded ZIP is empty."
        )

    if len(archive_content) > MAX_ZIP_SIZE_BYTES:
        raise BackupValidationError(
            "The ZIP is larger than the 50 MB limit."
        )

    try:
        archive_stream = BytesIO(archive_content)

        with zipfile.ZipFile(archive_stream, mode="r") as archive:
            entries = archive.infolist()

            if not entries:
                raise BackupValidationError(
                    "The ZIP is empty."
                )

            names = set()
            total_extracted_size = 0

            for info in entries:
                _validate_archive_entry(info)

                if info.filename in names:
                    raise BackupValidationError(
                        "The ZIP contains duplicate entries."
                    )

                names.add(info.filename)

                if not info.is_dir():
                    total_extracted_size += info.file_size

            if total_extracted_size > MAX_EXTRACTED_SIZE_BYTES:
                raise BackupValidationError(
                    "The extracted backup would exceed the 100 MB limit."
                )

            manifest = _read_and_validate_manifest(
                archive,
                names,
            )

            document_payloads = _read_document_payloads(
                archive,
                manifest,
                names,
            )

    except zipfile.BadZipFile as error:
        raise BackupValidationError(
            "The uploaded file is not a valid ZIP backup."
        ) from error

    new_chat_id = None
    chat_directory = None
    rag = RAGService()

    try:
        chat_payload = {
            "schema_version": manifest["schema_version"],
            "application": manifest["application"],
            "exported_at": manifest["exported_at"],
            "chat": manifest["chat"],
            "model": manifest["model"],
            "messages": manifest["messages"],
        }

        restore_result = restore_chat_backup(chat_payload)
        new_chat_id = int(restore_result["chat_id"])

        chat_directory = UPLOAD_DIR / f"chat_{new_chat_id}"
        chat_directory.mkdir(
            parents=True,
            exist_ok=False,
        )

        restored_documents = []
        total_pages = 0
        total_chunks = 0

        for payload in document_payloads:
            filename = payload["filename"]
            file_path = chat_directory / filename

            with open(file_path, "xb") as output_file:
                output_file.write(payload["content"])

            document = create_document(
                chat_id=new_chat_id,
                filename=filename,
                file_path=file_path,
                file_hash=payload["file_hash"],
                file_size=payload["file_size"],
            )

            indexing_result = rag.add_pdf(
                file_path=file_path,
                chat_id=new_chat_id,
                document_id=document["document_id"],
            )

            if indexing_result["chunks"] <= 0:
                raise BackupValidationError(
                    f"No readable text was found in {filename}."
                )

            ready_document = mark_document_ready(
                document_id=document["document_id"],
                chat_id=new_chat_id,
                page_count=indexing_result["pages"],
                chunk_count=indexing_result["chunks"],
            )

            if not payload["is_selected"]:
                ready_document = set_document_selected(
                    document_id=document["document_id"],
                    chat_id=new_chat_id,
                    is_selected=False,
                )

            total_pages += indexing_result["pages"]
            total_chunks += indexing_result["chunks"]
            restored_documents.append(ready_document)

        json_restore_warnings = [
            str(warning)
            for warning in restore_result.get("warnings", [])
            if "pdf" not in str(warning).lower()
            and "rag" not in str(warning).lower()
        ]

        manifest_warnings = manifest.get("warnings", [])

        if not isinstance(manifest_warnings, list):
            manifest_warnings = []

        return {
            **restore_result,
            "document_count": len(restored_documents),
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "documents": restored_documents,
            "warnings": [
                *json_restore_warnings,
                *[str(item) for item in manifest_warnings],
            ],
        }

    except Exception:
        if new_chat_id is not None:
            try:
                rag.delete_chat(new_chat_id)
            except Exception as cleanup_error:
                print("RAG CLEANUP ERROR:", cleanup_error)

            try:
                delete_chat_documents(new_chat_id)
            except Exception as cleanup_error:
                print("DOCUMENT CLEANUP ERROR:", cleanup_error)

            try:
                delete_chat(new_chat_id)
            except Exception as cleanup_error:
                print("CHAT CLEANUP ERROR:", cleanup_error)

        if chat_directory is not None and chat_directory.exists():
            shutil.rmtree(
                chat_directory,
                ignore_errors=True,
            )

        raise