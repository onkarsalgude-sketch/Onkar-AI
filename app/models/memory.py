"""Safe API models for conversational memory controls."""

from pydantic import BaseModel, Field


class MemoryPreview(BaseModel):
    role: str = Field(
        min_length=1,
        max_length=100,
    )
    preview: str = Field(
        min_length=1,
        max_length=240,
    )
    truncated: bool


class MemoryListResponse(BaseModel):
    service: str = "memory"
    items: list[MemoryPreview]
    returned: int = Field(
        ge=0,
        le=20,
    )
    limit: int = Field(
        ge=1,
        le=20,
    )


class MemoryClearResponse(BaseModel):
    service: str = "memory"
    cleared: bool
    message: str
