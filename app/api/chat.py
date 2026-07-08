from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatResponse
from app.agents.brain import Brain
from app.services.history_service import (
    init_db,
    create_chat,
    get_chats,
    save_message,
    get_messages,
    clear_history,
    delete_chat,
    rename_chat,
)
from app.memory.memory import clear

router = APIRouter()
brain = Brain()

init_db()


@router.post("/chats")
def create_new_chat():
    chat_id = create_chat("New Chat")
    return {"chat_id": chat_id, "title": "New Chat"}


@router.get("/chats")
def list_chats():
    return {"chats": get_chats()}


@router.get("/chats/{chat_id}/messages")
def chat_messages(chat_id: int):
    return {"messages": get_messages(chat_id)}


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: int):
    delete_chat(chat_id)
    return {"message": "Chat deleted"}


@router.put("/chats/{chat_id}")
def update_chat_title(chat_id: int, title: str):
    rename_chat(chat_id, title)
    return {"message": "Chat renamed"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(request.message)
        chat_id = create_chat(title)
    if chat_id is not None:
        messages = get_messages(chat_id)
        if len(messages) == 0:
            title = brain.ai.generate_title(request.message)
            rename_chat(chat_id, title)
        save_message(chat_id, "user", request.message)

        reply = brain.chat(request.message)

        save_message(chat_id, "assistant", reply)

        return ChatResponse(reply=reply)


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(request.message)
        chat_id = create_chat(title)

    messages = get_messages(chat_id)

    if len(messages) == 0:
        title = brain.ai.generate_title(request.message)
        rename_chat(chat_id, title)

    save_message(chat_id, "user", request.message)

    def stream_generator():
        full_reply = ""

        for chunk in brain.stream_chat(request.message):
            full_reply += chunk
            yield chunk

        save_message(chat_id, "assistant", full_reply)

    return StreamingResponse(stream_generator(), media_type="text/plain")


@router.get("/chat/history")
def chat_history():
    chats = get_chats()

    if not chats:
        return {"messages": []}

    latest_chat_id = chats[0]["id"]
    return {"messages": get_messages(latest_chat_id)}


@router.delete("/chat/history")
def delete_history():
    clear_history()
    clear()
    return {"message": "Chat history cleared"}