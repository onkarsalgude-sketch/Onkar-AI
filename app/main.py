from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Onkar AI")

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def root():
    return {"message": "Onkar AI is running 🚀"}

@app.post("/chat")
def chat(request: ChatRequest):
    return {
        "reply": f"Onkar AI received your message: {request.message}"
    }