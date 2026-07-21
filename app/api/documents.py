import logging
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from fastapi.responses import Response
from pydantic import BaseModel

from app.config.settings import UPLOAD_DIR
from app.services.rag_service import RAGService
from app.services.document_service import (
    calculate_file_hash,
    create_document,
    mark_document_ready,
    mark_document_failed,
    list_documents as list_document_records,
    get_document,
    get_document_by_filename,
    find_duplicate_document,
    set_document_selected,
    delete_document_record,
)
from app.services.document_object_service import (
    delete_document_object,
    get_document_storage,
    materialize_pdf_bytes,
    read_document_bytes,
    restore_document_vectors,
    store_document_bytes,
)
from app.storage.document_storage import (
    DocumentNotFoundError,
    DocumentStorageError,
)


router = APIRouter()
rag = RAGService()
logger = logging.getLogger(__name__)


class DocumentSelectionRequest(BaseModel):
    is_selected: bool


def get_safe_pdf_filename(
    filename: str | None,
) -> str:
    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename",
        )

    safe_filename = Path(filename).name

    if (
        safe_filename != filename
        or len(safe_filename) > 255
        or any(
            ord(character) < 32
            or ord(character) == 127
            for character in safe_filename
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename",
        )

    if (
        Path(safe_filename)
        .suffix
        .lower()
        != ".pdf"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    return safe_filename


def get_chat_upload_directory(chat_id: int) -> Path:
    if chat_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid chat ID",
        )

    return UPLOAD_DIR / f"chat_{chat_id}"


def get_chat_directory(chat_id: int) -> Path:
    chat_directory = get_chat_upload_directory(chat_id)
    chat_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return chat_directory


def resolve_chat_pdf_path(
    chat_id: int,
    filename: str,
) -> tuple[Path, str]:
    safe_filename = get_safe_pdf_filename(filename)
    chat_directory = get_chat_upload_directory(chat_id)
    file_path = (chat_directory / safe_filename).resolve(
        strict=False,
    )
    chat_directory_resolved = chat_directory.resolve(
        strict=False,
    )

    if not file_path.is_relative_to(
        chat_directory_resolved,
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return file_path, safe_filename


@router.post("/documents/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    chat_id: int = Form(...),
):
    if chat_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid chat ID",
        )

    safe_filename = get_safe_pdf_filename(
        file.filename
    )

    file_content = await file.read()

    if not file_content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded PDF is empty",
        )

    if b"%PDF-" not in file_content[:1024]:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid PDF",
        )

    file_hash = calculate_file_hash(
        file_content
    )

    duplicate_document = (
        find_duplicate_document(
            chat_id=chat_id,
            file_hash=file_hash,
        )
    )

    if duplicate_document:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "This PDF is already uploaded"
                ),
                "document_id": (
                    duplicate_document[
                        "document_id"
                    ]
                ),
                "filename": (
                    duplicate_document[
                        "filename"
                    ]
                ),
            },
        )

    previous_document = (
        get_document_by_filename(
            chat_id=chat_id,
            filename=safe_filename,
        )
    )

    document_id = (
        str(
            previous_document[
                "document_id"
            ]
        )
        if previous_document
        else uuid4().hex
    )

    storage = get_document_storage()

    try:
        object_key = store_document_bytes(
            chat_id=chat_id,
            document_id=document_id,
            filename=safe_filename,
            file_hash=file_hash,
            data=file_content,
            storage=storage,
        )
    except DocumentStorageError as error:
        logger.exception(
            "Document object upload failed"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Document storage is unavailable"
            ),
        ) from error

    document_written = False

    try:
        rag.delete_pdf(
            safe_filename,
            chat_id=chat_id,
        )

        with materialize_pdf_bytes(
            file_content,
            safe_filename,
        ) as temporary_path:
            result = rag.add_pdf(
                file_path=temporary_path,
                chat_id=chat_id,
                document_id=document_id,
            )

        if int(
            result.get(
                "chunks",
                0,
            )
            or 0
        ) <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No readable text found in PDF"
                ),
            )

        document = create_document(
            chat_id=chat_id,
            filename=safe_filename,
            file_path=object_key,
            file_hash=file_hash,
            file_size=len(file_content),
            document_id=document_id,
        )

        document_written = True

        ready_document = mark_document_ready(
            document_id=document[
                "document_id"
            ],
            chat_id=chat_id,
            page_count=int(
                result.get(
                    "pages",
                    0,
                )
                or 0
            ),
            chunk_count=int(
                result.get(
                    "chunks",
                    0,
                )
                or 0
            ),
        )

        if ready_document is None:
            raise RuntimeError(
                "Document ready state was not saved."
            )

    except Exception as error:
        try:
            rag.delete_pdf(
                safe_filename,
                chat_id=chat_id,
            )
        except Exception:
            logger.exception(
                "New document vector cleanup failed"
            )

        try:
            storage.delete(
                object_key
            )
        except Exception:
            logger.exception(
                "New document object cleanup failed"
            )

        if previous_document is not None:
            try:
                restore_document_vectors(
                    previous_document,
                    rag=rag,
                    storage=storage,
                )
            except Exception:
                logger.exception(
                    "Previous document vector rollback failed"
                )

        if document_written:
            try:
                mark_document_failed(
                    document_id=document_id,
                    chat_id=chat_id,
                )
            except Exception:
                logger.exception(
                    "Document failure state could not be saved"
                )

        if isinstance(
            error,
            HTTPException,
        ):
            raise

        logger.exception(
            "PDF indexing failed"
        )

        raise HTTPException(
            status_code=500,
            detail="PDF indexing failed",
        ) from error

    if previous_document is not None:
        previous_reference = str(
            previous_document.get(
                "file_path",
                "",
            )
        )

        if previous_reference != object_key:
            try:
                delete_document_object(
                    previous_document,
                    storage=storage,
                )
            except DocumentStorageError:
                logger.warning(
                    "Previous document object cleanup failed",
                    exc_info=True,
                )

    return {
        "message": (
            "PDF uploaded and indexed successfully"
        ),
        "document": ready_document,
    }


@router.get("/documents/search")
async def search_documents(
    query: str,
    chat_id: int,
):
    result = rag.search(
        query=query,
        chat_id=chat_id,
    )

    return {
        "chat_id": chat_id,
        "results": result["sources"],
        "context": result["context"],
    }


@router.get("/documents")
async def list_documents(chat_id: int):
    if chat_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid chat ID",
        )

    documents = list_document_records(chat_id)

    for document in documents:
        document["size_kb"] = round(
            document["file_size"] / 1024,
            2,
        )

    return {
        "chat_id": chat_id,
        "documents": documents,
    }


@router.put(
    "/documents/{document_id}/selection"
)
async def update_document_selection(
    document_id: str,
    chat_id: int,
    request: DocumentSelectionRequest,
):
    document = get_document(
        document_id=document_id,
        chat_id=chat_id,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    updated_document = set_document_selected(
        document_id=document_id,
        chat_id=chat_id,
        is_selected=request.is_selected,
    )

    return {
        "message": "Document selection updated",
        "document": updated_document,
    }


@router.get(
    "/documents/{filename}/preview",
    operation_id="preview_pdf_get",
)
@router.head(
    "/documents/{filename}/preview",
    operation_id="preview_pdf_head",
    include_in_schema=False,
)
async def preview_pdf(
    filename: str,
    chat_id: int,
):
    safe_filename = get_safe_pdf_filename(
        filename
    )

    document = get_document_by_filename(
        chat_id=chat_id,
        filename=safe_filename,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        file_content = read_document_bytes(
            document
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        ) from error
    except DocumentStorageError as error:
        logger.exception(
            "Document preview storage failure"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Document storage is unavailable"
            ),
        ) from error

    encoded_filename = quote(
        safe_filename,
        safe="",
    )

    return Response(
        content=file_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                "inline; "
                "filename*=UTF-8''"
                f"{encoded_filename}"
            ),
            "Content-Length": str(
                len(file_content)
            ),
            "Cache-Control": (
                "private, no-store"
            ),
            "X-Content-Type-Options": (
                "nosniff"
            ),
        },
    )


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    chat_id: int,
):
    safe_filename = get_safe_pdf_filename(
        filename
    )

    document = get_document_by_filename(
        chat_id=chat_id,
        filename=safe_filename,
    )

    file_deleted = False

    if document is not None:
        try:
            file_deleted = (
                delete_document_object(
                    document
                )
            )
        except DocumentStorageError as error:
            logger.exception(
                "Document object deletion failed"
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "Document storage is unavailable"
                ),
            ) from error

    vector_result = rag.delete_pdf(
        safe_filename,
        chat_id=chat_id,
    )

    record_deleted = False

    if document is not None:
        record_deleted = (
            delete_document_record(
                document_id=document[
                    "document_id"
                ],
                chat_id=chat_id,
            )
        )

    if (
        not file_deleted
        and not record_deleted
        and vector_result[
            "deleted_chunks"
        ] == 0
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Document not found in this chat"
            ),
        )

    return {
        "message": (
            "Document deleted successfully"
        ),
        "filename": safe_filename,
        "chat_id": chat_id,
        "file_deleted": file_deleted,
        "record_deleted": record_deleted,
        "deleted_chunks": vector_result[
            "deleted_chunks"
        ],
    }
