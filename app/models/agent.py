from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.agents.registry import (
    MAX_AGENT_ID_LENGTH,
)


MAX_AGENT_NAME_LENGTH = 120
MAX_AGENT_DESCRIPTION_LENGTH = 1000
MAX_AGENT_CAPABILITY_LENGTH = 120
MAX_AGENT_CAPABILITIES = 32
MAX_AGENT_CATALOG_SIZE = 32

AgentCapability = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_AGENT_CAPABILITY_LENGTH,
    ),
]


class AgentCatalogItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    agent_id: str = Field(
        min_length=1,
        max_length=MAX_AGENT_ID_LENGTH,
    )
    name: str = Field(
        min_length=1,
        max_length=MAX_AGENT_NAME_LENGTH,
    )
    description: str = Field(
        min_length=1,
        max_length=MAX_AGENT_DESCRIPTION_LENGTH,
    )
    capabilities: tuple[
        AgentCapability,
        ...,
    ] = Field(
        min_length=1,
        max_length=MAX_AGENT_CAPABILITIES,
    )


class AgentCatalogResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    agents: tuple[
        AgentCatalogItem,
        ...,
    ] = Field(
        min_length=1,
        max_length=MAX_AGENT_CATALOG_SIZE,
    )
