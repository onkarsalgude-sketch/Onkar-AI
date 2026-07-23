from __future__ import annotations

from dataclasses import dataclass

from app.agents.registry import (
    GENERAL_CHAT_AGENT_ID,
    MAX_AGENT_ID_LENGTH,
    AgentRegistry,
    AgentRegistryError,
    build_default_agent_registry,
)


class AgentSelectionError(RuntimeError):
    """Raised when an explicit agent cannot be selected safely."""


@dataclass(
    frozen=True,
    slots=True,
)
class AgentSelectionResult:
    agent_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    used_default: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.agent_id, str)
            or not self.agent_id
            or not isinstance(self.name, str)
            or not self.name
            or not isinstance(
                self.description,
                str,
            )
            or not self.description
            or not isinstance(
                self.capabilities,
                tuple,
            )
            or not self.capabilities
            or any(
                not isinstance(
                    capability,
                    str,
                )
                or not capability
                for capability
                in self.capabilities
            )
            or not isinstance(
                self.used_default,
                bool,
            )
        ):
            raise AgentSelectionError(
                "Unable to select agent."
            )


def _selection_registry(
    value: AgentRegistry | None,
) -> AgentRegistry:
    if value is None:
        return build_default_agent_registry()

    if not isinstance(
        value,
        AgentRegistry,
    ):
        raise AgentSelectionError(
            "Unable to select agent."
        )

    return value


def _selection_id(
    value: str | None,
) -> tuple[str, bool]:
    if value is None:
        return (
            GENERAL_CHAT_AGENT_ID,
            True,
        )

    if not isinstance(value, str):
        raise AgentSelectionError(
            "Unable to select agent."
        )

    resolved = value.strip()

    if (
        not resolved
        or len(resolved)
        > MAX_AGENT_ID_LENGTH
    ):
        raise AgentSelectionError(
            "Unable to select agent."
        )

    return resolved, False


def resolve_agent_selection(
    agent_id: str | None = None,
    *,
    registry: AgentRegistry | None = None,
) -> AgentSelectionResult:
    resolved_registry = (
        _selection_registry(registry)
    )
    resolved_id, used_default = (
        _selection_id(agent_id)
    )

    try:
        definition = (
            resolved_registry.require(
                resolved_id
            )
        )
    except AgentRegistryError as error:
        raise AgentSelectionError(
            "Unable to select agent."
        ) from error

    record = definition.public_record()

    return AgentSelectionResult(
        agent_id=record["agent_id"],
        name=record["name"],
        description=(
            record["description"]
        ),
        capabilities=tuple(
            record["capabilities"]
        ),
        used_default=used_default,
    )
