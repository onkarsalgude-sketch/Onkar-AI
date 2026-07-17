import json
import shutil
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents.brain import Brain
from app.config.settings import UPLOAD_DIR
from app.memory.memory import clear
from app.models.chat import (
    ChatBackupImportRequest,
    ChatBackupImportResponse,
    ChatRequest,
    ChatResponse,
    MessageDeleteResponse,
    MessageEditRequest,
    MessageEditResponse,
    MessageRegenerateRequest,
)
from app.services.history_service import (
    clear_history,
    create_chat,
    create_folder,
    delete_chat,
    delete_folder,
    delete_message,
    edit_user_message,
    get_chats,
    get_folders,
    get_message,
    get_messages,
    init_db,
    move_chat_to_folder,
    rename_chat,
    rename_folder,
    restore_chat_backup,
    save_message,
    search_chats,
    toggle_pin_chat,
)


router = APIRouter()
brain = Brain()

init_db()


# -------------------------
# Available AI models
# -------------------------

@router.get("/models")
def list_models():
    return {
        "models": brain.ai.get_available_models(),
        "default_model": brain.ai.default_model,
    }


# -------------------------
# Chat management
# -------------------------

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


@router.get("/chats/search")
def global_chat_search(
    q: str,
    role: str | None = None,
    folder_id: int | None = None,
    limit: int = 50,
):
    search_query = str(q or "").strip()

    if len(search_query) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Enter at least 2 characters "
                "to search."
            ),
        )

    if len(search_query) > 200:
        raise HTTPException(
            status_code=400,
            detail=(
                "Search text cannot exceed "
                "200 characters."
            ),
        )

    if role not in {
        None,
        "user",
        "assistant",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Role must be 'user' or "
                "'assistant'."
            ),
        )

    if (
        folder_id is not None
        and folder_id < 0
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Folder ID must be 0 or "
                "a positive integer."
            ),
        )

    safe_limit = max(
        1,
        min(limit, 100),
    )

    try:
        results = search_chats(
            search_query,
            role=role,
            folder_id=folder_id,
            limit=safe_limit,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        print(
            "GLOBAL CHAT SEARCH ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to search chat "
                "history."
            ),
        ) from error

    return {
        "query": search_query,
        "count": len(results),
        "results": results,
    }


@router.post(
    "/chats/import",
    response_model=ChatBackupImportResponse,
)
def import_chat_backup(
    request: ChatBackupImportRequest,
):
    if (
        request.application.strip().lower()
        != "onkar ai"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "This backup was not created "
                "by Onkar AI."
            ),
        )

    try:
        result = restore_chat_backup(
            request.model_dump(mode="json")
        )
    except Exception as error:
        print(
            "CHAT BACKUP IMPORT ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to restore the chat "
                "backup."
            ),
        ) from error

    return ChatBackupImportResponse(
        **result
    )


@router.get("/chats/{chat_id}/messages")
def chat_messages(chat_id: int):
    return {
        "messages": get_messages(chat_id),
    }

@router.patch(
    "/chats/{chat_id}/messages/{message_id}",
    response_model=MessageEditResponse,
)
def update_user_message(
    chat_id: int,
    message_id: int,
    request: MessageEditRequest,
):
    try:
        result = edit_user_message(
            chat_id,
            message_id,
            request.content,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        print(
            "MESSAGE EDIT ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to edit the message.",
        ) from error

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    return MessageEditResponse(
        message="Message updated successfully.",
        **result,
    )


@router.delete(
    "/chats/{chat_id}/messages/{message_id}",
    response_model=MessageDeleteResponse,
)
def remove_message(
    chat_id: int,
    message_id: int,
):
    try:
        result = delete_message(
            chat_id,
            message_id,
        )

    except Exception as error:
        print(
            "MESSAGE DELETE ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to delete the message.",
        ) from error

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    return MessageDeleteResponse(
        message="Message deleted successfully.",
        **result,
    )


@router.post(
    "/chats/{chat_id}/messages/{message_id}/regenerate"
)
def regenerate_message_response(
    chat_id: int,
    message_id: int,
    request: MessageRegenerateRequest,
):
    original_message = get_message(
        chat_id,
        message_id,
    )

    if original_message is None:
        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    if original_message["role"] != "user":
        raise HTTPException(
            status_code=400,
            detail=(
                "A response can only be regenerated "
                "from a user message."
            ),
        )

    if original_message.get("attachment"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Attachment messages cannot be "
                "regenerated yet."
            ),
        )

    try:
        # जुना assistant response आणि त्यानंतरचे
        # messages remove करून context सुरक्षित ठेवणे.
        edit_result = edit_user_message(
            chat_id,
            message_id,
            original_message["content"],
        )

        result = brain.chat(
            original_message["content"],
            chat_id=chat_id,
            model_id=request.model_id,
        )

        result_sources = (
            result.get("sources")
            or []
        )

        result_model_id = (
            result.get("model_id")
            or request.model_id
        )

        save_message(
            chat_id,
            "assistant",
            result["reply"],
            sources=result_sources,
            model_id=result_model_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        print(
            "MESSAGE REGENERATE ERROR:",
            error,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to regenerate the response."
            ),
        ) from error

    return {
        "message": "Response regenerated successfully.",
        "chat_id": chat_id,
        "user_message_id": message_id,
        "reply": result["reply"],
        "sources": result_sources,
        "model_id": result_model_id,
        "deleted_following_messages": (
            edit_result[
                "deleted_following_messages"
            ]
        ),
    }

@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: int):
    # त्या chat चे ChromaDB chunks delete करणे
    vector_result = brain.rag.delete_chat(chat_id)

    # त्या chat चा uploaded PDF folder delete करणे
    chat_directory = (
        UPLOAD_DIR / f"chat_{chat_id}"
    )

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
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    return {
        "message": (
            "Chat pinned"
            if is_pinned
            else "Chat unpinned"
        ),
        "chat_id": chat_id,
        "is_pinned": is_pinned,
    }


# -------------------------
# Folder management
# -------------------------

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


# -------------------------
# Normal chat
# -------------------------

@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(
            request.message,
            model_id=request.model_id,
        )

        chat_id = create_chat(title)

    messages = get_messages(chat_id)

    if len(messages) == 0:
        title = brain.ai.generate_title(
            request.message,
            model_id=request.model_id,
        )

        rename_chat(chat_id, title)

    save_message(
        chat_id,
        "user",
        request.message,
    )

    result = brain.chat(
        request.message,
        chat_id=chat_id,
        model_id=request.model_id,
    )

    result_sources = (
        result.get("sources")
        or []
    )

    result_model_id = (
        result.get("model_id")
        or request.model_id
    )

    save_message(
        chat_id,
        "assistant",
        result["reply"],
        sources=result_sources,
        model_id=result_model_id,
    )

    return ChatResponse(
        reply=result["reply"],
        sources=result_sources,
        chat_id=chat_id,
    )


# -------------------------
# Streaming chat
# -------------------------

@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    chat_id = request.chat_id

    if chat_id is None:
        title = brain.ai.generate_title(
            request.message,
            model_id=request.model_id,
        )

        chat_id = create_chat(title)

    messages = get_messages(chat_id)

    if len(messages) == 0:
        title = brain.ai.generate_title(
            request.message,
            model_id=request.model_id,
        )

        rename_chat(chat_id, title)

    save_message(
        chat_id,
        "user",
        request.message,
    )

    stream_result = brain.stream_chat(
        request.message,
        chat_id=chat_id,
        model_id=request.model_id,
    )

    stream_sources = (
        stream_result.get("sources")
        or []
    )

    stream_model_id = (
        stream_result.get("model_id")
        or request.model_id
        or ""
    )

    sources_header = quote(
        json.dumps(
            stream_sources,
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
                sources=stream_sources,
                model_id=(
                    stream_model_id
                    or None
                ),
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
            "X-Model-Id": stream_model_id,
        },
    )


# -------------------------
# History
# -------------------------

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