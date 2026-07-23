from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


MAX_AGENT_ID_LENGTH = 64
MAX_AGENT_NAME_LENGTH = 80
MAX_AGENT_DESCRIPTION_LENGTH = 500
MAX_AGENT_CAPABILITIES = 16
MAX_AGENT_CAPABILITY_LENGTH = 64
MAX_AGENT_MESSAGE_LENGTH = 20_000
MAX_MODEL_ID_LENGTH = 128

GENERAL_CHAT_AGENT_ID = "general-chat"
GENERAL_CHAT_CAPABILITY = "chat.respond"

_AGENT_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_-]{0,63}$"
)
_CAPABILITY_PATTERN = re.compile(
    r"^[a-z][a-z0-9._:-]{0,63}$"
)
_MODEL_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
)


class AgentRegistryError(RuntimeError):
    """Base error for the static Agent Registry."""


class AgentRegistryValidationError(
    AgentRegistryError
):
    """Raised when an Agent Registry contract is invalid."""


class AgentAlreadyRegisteredError(
    AgentRegistryError
):
    """Raised when an agent ID is registered twice."""


class AgentNotFoundError(AgentRegistryError):
    """Raised when a requested agent ID is unavailable."""


class AgentDispatchError(AgentRegistryError):
    """Raised when a registered agent cannot dispatch safely."""


def _bounded_text(
    value: Any,
    *,
    field_name: str,
    maximum: int,
) -> str:
    if not isinstance(value, str):
        raise AgentRegistryValidationError(
            f"Invalid {field_name}."
        )

    candidate = " ".join(
        value.split()
    )

    if (
        not candidate
        or len(candidate) > maximum
        or any(
            ord(character) < 32
            for character in candidate
        )
    ):
        raise AgentRegistryValidationError(
            f"Invalid {field_name}."
        )

    return candidate


def _agent_id(value: Any) -> str:
    if not isinstance(value, str):
        raise AgentRegistryValidationError(
            "Invalid agent ID."
        )

    if (
        value != value.strip()
        or len(value) > MAX_AGENT_ID_LENGTH
        or not _AGENT_ID_PATTERN.fullmatch(value)
    ):
        raise AgentRegistryValidationError(
            "Invalid agent ID."
        )

    return value


def _capabilities(
    values: Any,
) -> tuple[str, ...]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Iterable)
    ):
        raise AgentRegistryValidationError(
            "Invalid agent capabilities."
        )

    resolved: list[str] = []
    seen: set[str] = set()

    for value in values:
        if (
            not isinstance(value, str)
            or value != value.strip()
            or len(value)
            > MAX_AGENT_CAPABILITY_LENGTH
            or not _CAPABILITY_PATTERN.fullmatch(
                value
            )
        ):
            raise AgentRegistryValidationError(
                "Invalid agent capabilities."
            )

        if value in seen:
            raise AgentRegistryValidationError(
                "Duplicate agent capability."
            )

        seen.add(value)
        resolved.append(value)

        if (
            len(resolved)
            > MAX_AGENT_CAPABILITIES
        ):
            raise AgentRegistryValidationError(
                "Too many agent capabilities."
            )

    if not resolved:
        raise AgentRegistryValidationError(
            "Agent capabilities are required."
        )

    return tuple(
        sorted(resolved)
    )


def _chat_id(value: Any) -> int | None:
    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise AgentRegistryValidationError(
            "Invalid chat ID."
        )

    return value


def _model_id(value: Any) -> str | None:
    if value is None:
        return None

    if (
        not isinstance(value, str)
        or value != value.strip()
        or len(value) > MAX_MODEL_ID_LENGTH
        or not _MODEL_ID_PATTERN.fullmatch(
            value
        )
    ):
        raise AgentRegistryValidationError(
            "Invalid model ID."
        )

    return value


@dataclass(
    frozen=True,
    slots=True,
)
class AgentDispatchRequest:
    message: str
    chat_id: int | None = None
    model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message",
            _bounded_text(
                self.message,
                field_name="agent message",
                maximum=MAX_AGENT_MESSAGE_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "chat_id",
            _chat_id(self.chat_id),
        )
        object.__setattr__(
            self,
            "model_id",
            _model_id(self.model_id),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class AgentDispatchResult:
    agent_id: str
    route: str
    prompt: str
    sources: tuple[
        MappingProxyType,
        ...,
    ] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_id",
            _agent_id(self.agent_id),
        )
        object.__setattr__(
            self,
            "route",
            _bounded_text(
                self.route,
                field_name="agent route",
                maximum=64,
            ),
        )
        object.__setattr__(
            self,
            "prompt",
            _bounded_text(
                self.prompt,
                field_name="agent prompt",
                maximum=MAX_AGENT_MESSAGE_LENGTH,
            ),
        )

        if not isinstance(
            self.sources,
            tuple,
        ):
            raise AgentRegistryValidationError(
                "Invalid agent sources."
            )

        safe_sources: list[
            MappingProxyType
        ] = []

        for source in self.sources:
            if not isinstance(
                source,
                dict,
            ):
                raise AgentRegistryValidationError(
                    "Invalid agent sources."
                )

            safe_sources.append(
                MappingProxyType(
                    dict(source)
                )
            )

        object.__setattr__(
            self,
            "sources",
            tuple(safe_sources),
        )


AgentHandler = Callable[
    [AgentDispatchRequest],
    AgentDispatchResult,
]


@dataclass(
    frozen=True,
    slots=True,
)
class AgentDefinition:
    agent_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    handler: AgentHandler = field(
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_id",
            _agent_id(self.agent_id),
        )
        object.__setattr__(
            self,
            "name",
            _bounded_text(
                self.name,
                field_name="agent name",
                maximum=MAX_AGENT_NAME_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "description",
            _bounded_text(
                self.description,
                field_name="agent description",
                maximum=(
                    MAX_AGENT_DESCRIPTION_LENGTH
                ),
            ),
        )
        object.__setattr__(
            self,
            "capabilities",
            _capabilities(
                self.capabilities
            ),
        )

        if (
            isinstance(self.handler, str)
            or not callable(self.handler)
        ):
            raise AgentRegistryValidationError(
                "Agent handler must be a "
                "direct callable."
            )

    def public_record(
        self,
    ) -> MappingProxyType:
        return MappingProxyType(
            {
                "agent_id": self.agent_id,
                "name": self.name,
                "description": (
                    self.description
                ),
                "capabilities": (
                    self.capabilities
                ),
            }
        )


def dispatch_general_chat(
    request: AgentDispatchRequest,
) -> AgentDispatchResult:
    if not isinstance(
        request,
        AgentDispatchRequest,
    ):
        raise AgentRegistryValidationError(
            "Invalid agent dispatch request."
        )

    return AgentDispatchResult(
        agent_id=GENERAL_CHAT_AGENT_ID,
        route="chat",
        prompt=request.message,
        sources=(),
    )


class AgentRegistry:
    """Static, explicit registry for trusted agent callables."""

    def __init__(
        self,
        definitions: Iterable[
            AgentDefinition
        ] = (),
    ) -> None:
        self._definitions: dict[
            str,
            AgentDefinition,
        ] = {}

        for definition in definitions:
            self.register(definition)

    def register(
        self,
        definition: AgentDefinition,
    ) -> None:
        if not isinstance(
            definition,
            AgentDefinition,
        ):
            raise AgentRegistryValidationError(
                "Invalid agent definition."
            )

        if (
            definition.agent_id
            in self._definitions
        ):
            raise AgentAlreadyRegisteredError(
                "Agent ID is already registered."
            )

        self._definitions[
            definition.agent_id
        ] = definition

    def get(
        self,
        agent_id: str,
    ) -> AgentDefinition | None:
        resolved_id = _agent_id(agent_id)
        return self._definitions.get(
            resolved_id
        )

    def require(
        self,
        agent_id: str,
    ) -> AgentDefinition:
        definition = self.get(agent_id)

        if definition is None:
            raise AgentNotFoundError(
                "Agent is not registered."
            )

        return definition

    def list_agents(
        self,
    ) -> tuple[
        MappingProxyType,
        ...,
    ]:
        return tuple(
            self._definitions[
                agent_id
            ].public_record()
            for agent_id in sorted(
                self._definitions
            )
        )

    def dispatch(
        self,
        agent_id: str,
        request: AgentDispatchRequest,
    ) -> AgentDispatchResult:
        if not isinstance(
            request,
            AgentDispatchRequest,
        ):
            raise AgentRegistryValidationError(
                "Invalid agent dispatch request."
            )

        definition = self.require(
            agent_id
        )

        try:
            result = definition.handler(
                request
            )
        except AgentRegistryError:
            raise
        except Exception as error:
            raise AgentDispatchError(
                "Agent dispatch failed."
            ) from error

        if (
            not isinstance(
                result,
                AgentDispatchResult,
            )
            or result.agent_id
            != definition.agent_id
        ):
            raise AgentDispatchError(
                "Agent dispatch failed."
            )

        return result


def build_default_agent_registry(
) -> AgentRegistry:
    from app.agents.study import (
        build_study_agent_definition,
    )

    return AgentRegistry(
        (
            AgentDefinition(
                agent_id=(
                    GENERAL_CHAT_AGENT_ID
                ),
                name="General Chat",
                description=(
                    "Handles normal conversational "
                    "requests without a specialized "
                    "agent."
                ),
                capabilities=(
                    GENERAL_CHAT_CAPABILITY,
                ),
                handler=(
                    dispatch_general_chat
                ),
            ),
            build_study_agent_definition(),
        )
    )
