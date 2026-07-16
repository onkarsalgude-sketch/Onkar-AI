from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[int] = None
    model_id: Optional[str] = None


class Source(BaseModel):
    type: Optional[str] = None
    title: str
    url: Optional[str] = None
    filename: Optional[str] = None
    page: Optional[int] = None
    chat_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(
        default_factory=list
    )


# -------------------------
# Chat backup import models
# -------------------------

class ChatBackupSource(BaseModel):
    type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    title: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    url: Optional[str] = Field(
        default=None,
        max_length=4000,
    )

    filename: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    page: Optional[int] = Field(
        default=None,
        ge=1,
    )

    chat_id: Optional[int] = None

    domain: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class ChatBackupAttachment(BaseModel):
    filename: str = Field(
        min_length=1,
        max_length=255,
    )

    type: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    size: Optional[str] = Field(
        default=None,
        max_length=100,
    )


class ChatBackupMessage(BaseModel):
    index: Optional[int] = Field(
        default=None,
        ge=1,
    )

    role: Literal[
        "user",
        "assistant",
    ]

    content: str = Field(
        default="",
        max_length=200000,
    )

    model_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    created_at: Optional[datetime] = None

    attachment: Optional[
        ChatBackupAttachment
    ] = None

    sources: list[
        ChatBackupSource
    ] = Field(
        default_factory=list,
        max_length=100,
    )


class ChatBackupChatMetadata(BaseModel):
    id: Optional[int] = None

    title: str = Field(
        default="Imported Chat",
        max_length=200,
    )

    created_at: Optional[datetime] = None

    is_pinned: bool = False

    # Accepted for schema compatibility,
    # but import logic must not reuse an old folder ID.
    folder_id: Optional[int] = None

    folder_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )


class ChatBackupModelMetadata(BaseModel):
    selected_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    selected_name: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    default_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class ChatBackupImportRequest(BaseModel):
    schema_version: int = Field(
        ge=1,
        le=1,
    )

    application: str = Field(
        default="Onkar AI",
        max_length=100,
    )

    exported_at: Optional[datetime] = None

    chat: ChatBackupChatMetadata

    model: Optional[
        ChatBackupModelMetadata
    ] = None

    messages: list[
        ChatBackupMessage
    ] = Field(
        min_length=1,
        max_length=1000,
    )


class ChatBackupImportResponse(BaseModel):
    chat_id: int
    title: str
    message_count: int

    warnings: list[str] = Field(
        default_factory=list
    )