from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
)

from app.config.settings import UPLOAD_DIR
from app.services.rag_service import RAGService


router = APIRouter()
rag = RAGService()


def get_safe_pdf_filename(filename: str | None) -> str:
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


@router.post("/documents/upload")
async def upload_pdf(file: UploadFile = File(...)):
    safe_filename = get_safe_pdf_filename(file.filename)

    file_path = UPLOAD_DIR / safe_filename
    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_content = await file.read()

    if not file_content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded PDF is empty",
        )

    # त्याच नावाचा PDF आधी upload झाला असेल,
    # तर त्याचे जुने vectors delete करा.
    rag.delete_pdf(safe_filename)

    with open(file_path, "wb") as saved_file:
        saved_file.write(file_content)

    try:
        result = rag.add_pdf(file_path)
    except Exception as error:
        # Indexing fail झाल्यास incomplete file काढून टाका.
        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=f"PDF indexing failed: {error}",
        )

    return result


@router.get("/documents/search")
async def search_documents(query: str):
    result = rag.search(query)

    return {
        "results": result["sources"],
        "context": result["context"],
    }


@router.get("/documents")
async def list_documents():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    files = []

    for file_path in UPLOAD_DIR.glob("*.pdf"):
        files.append(
            {
                "name": file_path.name,
                "size": round(
                    file_path.stat().st_size / 1024,
                    2,
                ),
            }
        )

    files.sort(
        key=lambda item: item["name"].lower()
    )

    return {"documents": files}


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    safe_filename = get_safe_pdf_filename(filename)
    file_path = UPLOAD_DIR / safe_filename

    vector_result = rag.delete_pdf(safe_filename)
    file_deleted = False

    if file_path.exists():
        file_path.unlink()
        file_deleted = True

    if (
        not file_deleted
        and vector_result["deleted_chunks"] == 0
    ):
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return {
        "message": "Document deleted successfully",
        "filename": safe_filename,
        "file_deleted": file_deleted,
        "deleted_chunks": vector_result[
            "deleted_chunks"
        ],
    }