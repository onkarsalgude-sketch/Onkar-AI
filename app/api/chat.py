from fastapi import APIRouter

from app.models.chat import ChatRequest, ChatResponse
from app.agents.brain import Brain

router = APIRouter()

brain = Brain()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    reply = brain.chat(request.message)
    return ChatResponse(reply=reply)