from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str