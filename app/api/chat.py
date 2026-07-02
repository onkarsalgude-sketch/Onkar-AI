from fastapi import APIRouter

from app.models.chat import ChatRequest, ChatResponse
from app.agents.brain import Brain
from app.services.history_service import init_db, save_message

router = APIRouter()

brain = Brain()

init_db()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    save_message("user", request.message)

    reply = brain.chat(request.message)

    save_message("assistant", reply)

    return ChatResponse(reply=reply)
from app.services.history_service import get_messages, clear_history
@router.get("/chat/history")
def chat_history():
    return {"messages": get_messages()}


@router.delete("/chat/history")
def delete_history():
    clear_history()
    return {"message": "Chat history cleared"}