from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
)

from app.config.settings import UPLOAD_DIR
from app.services.rag_service import RAGService


router = APIRouter()
rag = RAGService()


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

    # याच chat मध्ये याच नावाची जुनी PDF असेल
    # तर तिचे जुने vectors आधी delete होतील.
    rag.delete_pdf(
        safe_filename,
        chat_id=chat_id,
    )

    with open(file_path, "wb") as saved_file:
        saved_file.write(file_content)

    try:
        result = rag.add_pdf(
            file_path,
            chat_id=chat_id,
        )

    except Exception as error:
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
        **result,
        "chat_id": chat_id,
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
    chat_directory = get_chat_directory(chat_id)

    documents = []

    for file_path in chat_directory.glob("*.pdf"):
        documents.append(
            {
                "name": file_path.name,
                "size": round(
                    file_path.stat().st_size / 1024,
                    2,
                ),
                "chat_id": chat_id,
            }
        )

    documents.sort(
        key=lambda document: document[
            "name"
        ].lower()
    )

    return {
        "chat_id": chat_id,
        "documents": documents,
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

    vector_result = rag.delete_pdf(
        safe_filename,
        chat_id=chat_id,
    )

    file_deleted = False

    if file_path.exists():
        file_path.unlink()
        file_deleted = True

    try:
        chat_directory.rmdir()
    except OSError:
        pass

    if (
        not file_deleted
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
        "deleted_chunks": vector_result[
            "deleted_chunks"
        ],
    }