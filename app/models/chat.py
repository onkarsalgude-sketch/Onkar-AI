from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[int] = None
    model_id: Optional[str] = None


class Source(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(
        default_factory=list
    )