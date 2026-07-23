from __future__ import annotations

from app.agents.registry import (
    MAX_AGENT_MESSAGE_LENGTH,
    AgentDefinition,
    AgentDispatchRequest,
    AgentDispatchResult,
    AgentRegistryValidationError,
)


DOCUMENT_AGENT_ID = "document"
DOCUMENT_AGENT_ROUTE = "document"
DOCUMENT_AGENT_CAPABILITIES = (
    "document.draft",
    "document.resume",
    "document.rewrite",
    "document.summarize",
)

_DOCUMENT_PROMPT_PREFIX = (
    "You are Onkar AI's Document Agent. "
    "Prepare accurate, reusable text while preserving the "
    "user's facts and requested format. "
    "Document request: "
)

_DOCUMENT_PROMPT_SUFFIX = (
    " Document rules: "
    "First identify whether the request is drafting, rewriting, "
    "summarizing, or resume preparation. "
    "Preserve every user-provided name, date, number, education "
    "detail, employment detail, qualification, and constraint "
    "exactly unless the user explicitly asks for a correction. "
    "Never invent missing facts, achievements, employers, marks, "
    "dates, contact details, qualifications, citations, or "
    "supporting evidence. "
    "When an essential fact is missing, use a visible placeholder "
    "such as [MISSING: graduation year] instead of guessing. "
    "Preserve the requested language, tone, length, and output "
    "format. "
    "For rewriting, keep the original meaning unless the user "
    "requests a substantive change. "
    "For summarizing, use only information present in the request "
    "and clearly state when source material is incomplete. "
    "For resumes, keep claims specific, truthful, and supported by "
    "the supplied details. "
    "Do not claim that a PDF, DOCX, resume file, attachment, upload, "
    "or download was created unless a separate artifact tool "
    "actually created it. "
    "Return text content only."
)


def build_document_prompt(
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
        _DOCUMENT_PROMPT_PREFIX
        + request.message
        + _DOCUMENT_PROMPT_SUFFIX
    )

    if len(prompt) > MAX_AGENT_MESSAGE_LENGTH:
        raise AgentRegistryValidationError(
            "Document prompt is too long."
        )

    return prompt


def dispatch_document(
    request: AgentDispatchRequest,
) -> AgentDispatchResult:
    return AgentDispatchResult(
        agent_id=DOCUMENT_AGENT_ID,
        route=DOCUMENT_AGENT_ROUTE,
        prompt=build_document_prompt(
            request
        ),
        sources=(),
    )


def build_document_agent_definition(
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=DOCUMENT_AGENT_ID,
        name="Document Agent",
        description=(
            "Prepares safe prompts for drafting, "
            "rewriting, summarizing, and resumes."
        ),
        capabilities=(
            DOCUMENT_AGENT_CAPABILITIES
        ),
        handler=dispatch_document,
    )
