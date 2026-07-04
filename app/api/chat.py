from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatResponse
from app.agents.brain import Brain
from app.services.history_service import (
    init_db,
    save_message,
    get_messages,
    clear_history,
)
from app.memory.memory import clear

router = APIRouter()

brain = Brain()

init_db()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    save_message("user", request.message)

    reply = brain.chat(request.message)

    save_message("assistant", reply)

    return ChatResponse(reply=reply)


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    save_message("user", request.message)

    def stream_generator():
        full_reply = ""

        for chunk in brain.ai.generate_reply_stream(request.message):
            full_reply += chunk
            yield chunk

        save_message("assistant", full_reply)

    return StreamingResponse(stream_generator(), media_type="text/plain")


@router.get("/chat/history")
def chat_history():
    return {"messages": get_messages()}


@router.delete("/chat/history")
def delete_history():
    clear_history()
    clear()

    return {"message": "Chat history cleared"}