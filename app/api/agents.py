from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from app.agents.registry import (
    build_default_agent_registry,
)
from app.models.agent import (
    AgentCatalogItem,
    AgentCatalogResponse,
)


router = APIRouter(
    tags=["Agents"],
)


@router.get(
    "/agents",
    response_model=AgentCatalogResponse,
    operation_id="list_agents",
)
def list_agents() -> AgentCatalogResponse:
    try:
        records = (
            build_default_agent_registry()
            .list_agents()
        )

        agents = tuple(
            AgentCatalogItem(
                agent_id=record["agent_id"],
                name=record["name"],
                description=record[
                    "description"
                ],
                capabilities=tuple(
                    record["capabilities"]
                ),
            )
            for record in records
        )

        return AgentCatalogResponse(
            agents=agents
        )

    except Exception as error:
        raise HTTPException(
            status_code=(
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to load agents.",
        ) from error
