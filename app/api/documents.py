import os
from fastapi import APIRouter, UploadFile, File

from app.services.rag_service import RAGService

router = APIRouter()

rag = RAGService()


@router.post("/documents/upload")
async def upload_pdf(file: UploadFile = File(...)):
    file_path = os.path.join("app/uploads", file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    result = rag.add_pdf(file_path)
    return result


@router.get("/documents/search")
async def search_documents(query: str):
    results = rag.search(query)
    return {"results": results}