import json
import shutil
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatResponse
from app.agents.brain import Brain
from app.config.settings import UPLOAD_DIR
from app.services.history_service import (
    init_db,
    create_chat,
    get_chats,
    save_message,
    get_messages,
    clear_history,
    delete_chat,
    rename_chat,
    toggle_pin_chat,
    get_folders,
    create_folder,
    rename_folder,
    delete_folder,
    move_chat_to_folder,
)
from app.memory.memory import clear


router = APIRouter()
brain = Brain()

init_db()


@router.post("/chats")
def create_new_chat():
    chat_id = create_chat("New Chat")

    return {
        "chat_id": chat_id,
        "title": "New Chat",
    }


@router.get("/chats")
def list_chats():
    return {
        "chats": get_chats(),
    }


@router.get("/chats/{chat_id}/messages")
def chat_messages(chat_id: int):
    return {
        "messages": get_messages(chat_id),
    }


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: int):
    # त्या chat चे ChromaDB chunks delete करणे
    vector_result = brain.rag.delete_chat(chat_id)

    # त्या chat चा uploaded PDF folder delete करणे
    chat_directory = UPLOAD_DIR / f"chat_{chat_id}"

    if chat_directory.exists():
        shutil.rmtree(chat_directory)

    # SQLite मधून chat आणि messages delete करणे
    delete_chat(chat_id)

    return {
        "message": "Chat deleted successfully",
        "chat_id": chat_id,
        "deleted_pdf_chunks": vector_result[
            "deleted_chunks"
        ],
    }


@router.put("/chats/{chat_id}")
def update_chat_title(
    chat_id: int,
    title: str,
):
    rename_chat(chat_id, title)

    return {
        "message": "Chat renamed",
    }

@router.put("/chats/{chat_id}/pin")
def pin_or_unpin_chat(chat_id: int):
    is_pinned = toggle_pin_chat(chat_id)

    if is_pinned is None:
        return {
            "message": "Chat not found",
            "chat_id": chat_id,
        }

    return {
        "message": (
            "Chat pinned"
            if is_pinned
            else "Chat unpinned"
        ),
        "chat_id": chat_id,
        "is_pinned": is_pinned,
    }

@router.get("/folders")
def list_folders():
    return {
        "folders": get_folders(),
    }


@router.post("/folders")
def add_folder(name: str):
    folder = create_folder(name)

    if folder is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Folder name is empty or "
                "folder already exists."
            ),
        )

    return {
        "message": "Folder created",
        "folder": folder,
    }


@router.put("/folders/{folder_id}")
def update_folder_name(
    folder_id: int,
    name: str,
):
    updated = rename_folder(
        folder_id,
        name,
    )

    if not updated:
        raise HTTPException(
            status_code=400,
            detail=(
                "Folder not found, name is empty, "
                "or folder name already exists."
            ),
        )

    return {
        "message": "Folder renamed",
        "folder_id": folder_id,
        "name": name.strip(),
    }


@router.delete("/folders/{folder_id}")
def remove_folder(folder_id: int):
    deleted = delete_folder(folder_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Folder not found.",
        )

    return {
        "message": "Folder deleted",
        "folder_id": folder_id,
    }


@router.put("/chats/{chat_id}/folder")
def update_chat_folder(
    chat_id: int,
    folder_id: int | None = None,
):
    updated = move_chat_to_folder(
        chat_id,
        folder_id,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Chat or folder not found.",
        )

    return {
        "message": (
            "Chat moved to folder"
            if folder_id is not None
            else "Chat removed from folder"
        ),
        "chat_id": chat_id,
        "folder_id": folder_id,
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(
            request.message
        )

        chat_id = create_chat(title)

    messages = get_messages(chat_id)

    if len(messages) == 0:
        title = brain.ai.generate_title(
            request.message
        )

        rename_chat(chat_id, title)

    save_message(
        chat_id,
        "user",
        request.message,
    )

    # Current chat ID Brain ला pass करणे
    result = brain.chat(
        request.message,
        chat_id=chat_id,
    )

    save_message(
        chat_id,
        "assistant",
        result["reply"],
    )

    return ChatResponse(
        reply=result["reply"],
        sources=result["sources"],
        chat_id=chat_id,
    )


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(
            request.message
        )

        chat_id = create_chat(title)

    messages = get_messages(chat_id)

    if len(messages) == 0:
        title = brain.ai.generate_title(
            request.message
        )

        rename_chat(chat_id, title)

    save_message(
        chat_id,
        "user",
        request.message,
    )

    # Current chat ID Brain ला pass करणे
    stream_result = brain.stream_chat(
        request.message,
        chat_id=chat_id,
    )

    sources_header = quote(
        json.dumps(
            stream_result["sources"],
            ensure_ascii=False,
        )
    )

    def stream_generator():
        full_reply = ""

        try:
            for chunk in stream_result["stream"]:
                full_reply += chunk
                yield chunk

            save_message(
                chat_id,
                "assistant",
                full_reply,
            )

        except Exception as error:
            print("STREAM ERROR:", error)
            raise

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain",
        headers={
            "X-Sources": sources_header,
            "X-Chat-Id": str(chat_id),
        },
    )


@router.get("/chat/history")
def chat_history():
    chats = get_chats()

    if not chats:
        return {
            "messages": [],
        }

    latest_chat_id = chats[0]["id"]

    return {
        "messages": get_messages(
            latest_chat_id
        ),
    }


@router.delete("/chat/history")
def delete_history():
    clear_history()
    clear()

    return {
        "message": "Chat history cleared",
    }