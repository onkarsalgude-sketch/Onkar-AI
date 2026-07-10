from fastapi import APIRouter, UploadFile, File, HTTPException
import base64

from app.services.groq_service import GroqService

router = APIRouter(prefix="/image", tags=["Image"])

groq = GroqService()


@router.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{file.content_type};base64,{image_base64}"

        result = groq.analyze_image(image_url)

        return {
            "success": True,
            "result": result,
        }

    except Exception as e:
        print("VISION ERROR:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )