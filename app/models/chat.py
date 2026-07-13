from typing import Optional

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