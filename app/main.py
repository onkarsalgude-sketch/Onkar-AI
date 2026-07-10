from fastapi import FastAPI
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.image import router as image_router

app = FastAPI(title="Onkar AI")
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:5173|http://127\.0\.0\.1:5173",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Onkar AI is running 🚀"}


app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(image_router)