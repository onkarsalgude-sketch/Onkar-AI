from pydantic import BaseModel


class Source(BaseModel):
    title: str
    url: str
    domain: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = []