from __future__ import annotations

from app.agents.registry import (
    MAX_AGENT_MESSAGE_LENGTH,
    AgentDefinition,
    AgentDispatchRequest,
    AgentDispatchResult,
    AgentRegistryValidationError,
)


STUDY_AGENT_ID = "study"
STUDY_AGENT_ROUTE = "study"
STUDY_AGENT_CAPABILITIES = (
    "study.explain",
    "study.quiz",
    "study.revise",
)

_STUDY_PROMPT_PREFIX = (
    "You are Onkar AI's Study Agent. "
    "Help the learner understand and practise the topic "
    "in a clear, accurate, level-appropriate way. "
    "Student request: "
)

_STUDY_PROMPT_SUFFIX = (
    " Teaching rules: "
    "Use simple language unless the learner requests an "
    "advanced explanation. "
    "Explain concepts step by step and include a concise "
    "recap when useful. "
    "For quiz requests, ask focused questions and do not "
    "reveal answers until the learner asks. "
    "For revision requests, emphasize key points and useful "
    "practice prompts. "
    "Do not invent facts, sources, citations, marks, or exam "
    "requirements. "
    "Do not claim that a document or source was used unless "
    "the student request actually provides one."
)


def build_study_prompt(
    request: AgentDispatchRequest,
) -> str:
    if not isinstance(
        request,
        AgentDispatchRequest,
    ):
        raise AgentRegistryValidationError(
            "Invalid agent dispatch request."
        )

    prompt = (
        _STUDY_PROMPT_PREFIX
        + request.message
        + _STUDY_PROMPT_SUFFIX
    )

    if len(prompt) > MAX_AGENT_MESSAGE_LENGTH:
        raise AgentRegistryValidationError(
            "Study prompt is too long."
        )

    return prompt


def dispatch_study(
    request: AgentDispatchRequest,
) -> AgentDispatchResult:
    return AgentDispatchResult(
        agent_id=STUDY_AGENT_ID,
        route=STUDY_AGENT_ROUTE,
        prompt=build_study_prompt(
            request
        ),
        sources=(),
    )


def build_study_agent_definition(
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=STUDY_AGENT_ID,
        name="Study Agent",
        description=(
            "Prepares safe, structured prompts for "
            "explanations, quizzes, and revision."
        ),
        capabilities=(
            STUDY_AGENT_CAPABILITIES
        ),
        handler=dispatch_study,
    )
