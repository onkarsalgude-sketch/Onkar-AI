from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.services.export_service import (
    BackupValidationError,
    ChatBackupNotFoundError,
    MAX_ZIP_SIZE_BYTES,
    create_full_chat_backup,
    restore_full_chat_backup,
)


router = APIRouter(
    prefix="/backups",
    tags=["Backups"],
)


def _delete_temporary_file(
    file_path: str | Path,
) -> None:
    Path(file_path).unlink(
        missing_ok=True
    )


def _backup_error_status(
    error: BackupValidationError,
) -> int:
    message = str(error).lower()

    if (
        "larger than" in message
        or "exceed" in message
        or "too large" in message
    ):
        return 413

    return 400


@router.get(
    "/chats/{chat_id}/full",
)
async def export_full_chat_backup(
    chat_id: int,
):
    try:
        (
            backup_path,
            download_name,
        ) = await run_in_threadpool(
            create_full_chat_backup,
            chat_id,
        )

    except ChatBackupNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except BackupValidationError as error:
        raise HTTPException(
            status_code=_backup_error_status(
                error
            ),
            detail=str(error),
        ) from error

    except Exception as error:
        print(
            "FULL BACKUP EXPORT ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to create the full "
                "chat backup."
            ),
        ) from error

    return FileResponse(
        path=backup_path,
        media_type="application/zip",
        filename=download_name,
        background=BackgroundTask(
            _delete_temporary_file,
            backup_path,
        ),
    )


@router.post(
    "/chats/import/full",
)
async def import_full_chat_backup(
    file: UploadFile = File(...),
):
    filename = Path(
        file.filename or ""
    ).name

    if (
        not filename
        or Path(filename).suffix.lower()
        != ".zip"
    ):
        await file.close()

        raise HTTPException(
            status_code=400,
            detail=(
                "Please upload an Onkar AI "
                ".zip backup file."
            ),
        )

    try:
        archive_content = await file.read(
            MAX_ZIP_SIZE_BYTES + 1
        )

    finally:
        await file.close()

    if (
        len(archive_content)
        > MAX_ZIP_SIZE_BYTES
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "The ZIP backup is larger "
                "than the 50 MB limit."
            ),
        )

    try:
        result = await run_in_threadpool(
            restore_full_chat_backup,
            archive_content,
        )

    except BackupValidationError as error:
        raise HTTPException(
            status_code=_backup_error_status(
                error
            ),
            detail=str(error),
        ) from error

    except Exception as error:
        print(
            "FULL BACKUP IMPORT ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to restore the full "
                "chat backup."
            ),
        ) from error

    return result
