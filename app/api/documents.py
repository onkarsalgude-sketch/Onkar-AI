from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
)
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


router = APIRouter()
rag = RAGService()


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

    if safe_filename != filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename",
        )

    if Path(safe_filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    return safe_filename


def get_chat_directory(chat_id: int) -> Path:
    if chat_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid chat ID",
        )

    chat_directory = UPLOAD_DIR / f"chat_{chat_id}"
    chat_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return chat_directory


@router.post("/documents/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    chat_id: int = Form(...),
):
    safe_filename = get_safe_pdf_filename(
        file.filename
    )

    chat_directory = get_chat_directory(chat_id)
    file_path = chat_directory / safe_filename

    file_content = await file.read()

    if not file_content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded PDF is empty",
        )

    file_hash = calculate_file_hash(file_content)

    duplicate_document = find_duplicate_document(
        chat_id=chat_id,
        file_hash=file_hash,
    )

    if duplicate_document:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This PDF is already uploaded",
                "document_id": duplicate_document[
                    "document_id"
                ],
                "filename": duplicate_document[
                    "filename"
                ],
            },
        )

    # Delete old vectors when replacing a PDF
    # having the same filename.
    rag.delete_pdf(
        safe_filename,
        chat_id=chat_id,
    )

    with open(file_path, "wb") as saved_file:
        saved_file.write(file_content)

    document = create_document(
        chat_id=chat_id,
        filename=safe_filename,
        file_path=file_path,
        file_hash=file_hash,
        file_size=len(file_content),
    )

    try:
        result = rag.add_pdf(
            file_path=file_path,
            chat_id=chat_id,
            document_id=document["document_id"],
        )

        if result["chunks"] <= 0:
            mark_document_failed(
                document_id=document["document_id"],
                chat_id=chat_id,
            )

            raise HTTPException(
                status_code=422,
                detail="No readable text found in PDF",
            )

        ready_document = mark_document_ready(
            document_id=document["document_id"],
            chat_id=chat_id,
            page_count=result["pages"],
            chunk_count=result["chunks"],
        )

    except HTTPException:
        raise

    except Exception as error:
        mark_document_failed(
            document_id=document["document_id"],
            chat_id=chat_id,
        )

        if file_path.exists():
            file_path.unlink()

        try:
            chat_directory.rmdir()
        except OSError:
            pass

        raise HTTPException(
            status_code=500,
            detail=f"PDF indexing failed: {error}",
        )

    return {
        "message": "PDF uploaded and indexed successfully",
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


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    chat_id: int,
):
    safe_filename = get_safe_pdf_filename(
        filename
    )

    chat_directory = get_chat_directory(chat_id)
    file_path = chat_directory / safe_filename

    document = get_document_by_filename(
        chat_id=chat_id,
        filename=safe_filename,
    )

    vector_result = rag.delete_pdf(
        safe_filename,
        chat_id=chat_id,
    )

    file_deleted = False
    record_deleted = False

    if file_path.exists():
        file_path.unlink()
        file_deleted = True

    if document:
        record_deleted = delete_document_record(
            document_id=document["document_id"],
            chat_id=chat_id,
        )

    try:
        chat_directory.rmdir()
    except OSError:
        pass

    if (
        not file_deleted
        and not record_deleted
        and vector_result["deleted_chunks"] == 0
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found in this chat",
        )

    return {
        "message": "Document deleted successfully",
        "filename": safe_filename,
        "chat_id": chat_id,
        "file_deleted": file_deleted,
        "record_deleted": record_deleted,
        "deleted_chunks": vector_result[
            "deleted_chunks"
        ],
    }