import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File

router = APIRouter()


@router.post("/documents/upload")
async def upload_pdf(file: UploadFile = File(...)):
    os.makedirs("app/uploads", exist_ok=True)

    file_path = os.path.join("app/uploads", file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    return {
        "message": "PDF uploaded successfully. RAG is disabled on cloud free tier.",
        "chunks": 0
    }


@router.get("/documents/search")
async def search_documents(query: str):
    return {"results": []}


@router.get("/documents")
async def list_documents():
    upload_path = Path("app/uploads")
    upload_path.mkdir(parents=True, exist_ok=True)

    files = []

    for file in upload_path.glob("*.pdf"):
        files.append({
            "name": file.name,
            "size": round(file.stat().st_size / 1024, 2)
        })

    return {"documents": files}


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    file_path = Path("app/uploads") / filename

    if not file_path.exists():
        return {"message": "File not found"}

    file_path.unlink()

    return {"message": "Document deleted", "filename": filename}