from __future__ import annotations

from app.agents.registry import (
    MAX_AGENT_MESSAGE_LENGTH,
    AgentDefinition,
    AgentDispatchRequest,
    AgentDispatchResult,
    AgentRegistryValidationError,
)


CODING_AGENT_ID = "coding"
CODING_AGENT_ROUTE = "coding"
CODING_AGENT_CAPABILITIES = (
    "coding.debug",
    "coding.explain",
    "coding.review",
    "coding.write",
)

_CODING_PROMPT_PREFIX = (
    "You are Onkar AI's Coding Agent. "
    "Help with software development in a clear, accurate, "
    "and practical way. "
    "Developer request: "
)

_CODING_PROMPT_SUFFIX = (
    " Coding rules: "
    "Preserve the requested language, framework, platform, "
    "and constraints. "
    "When code is requested, provide complete usable code "
    "with sensible validation and error handling. "
    "Explain important assumptions and trade-offs. "
    "For debugging, identify the likely cause before giving "
    "the corrected code. "
    "For reviews, separate confirmed defects from optional "
    "improvements. "
    "Never claim code was executed, tested, deployed, or "
    "verified unless actual tool output proves it. "
    "Clearly label code as untested when it has not been run. "
    "Do not invent files, APIs, package versions, logs, "
    "benchmarks, or execution results."
)

_SAFE_REDIRECT_PROMPT = (
    "You are Onkar AI's Coding Agent. "
    "The developer request appears to involve destructive, "
    "credential-stealing, malware, persistence, evasion, or "
    "unauthorized-access behavior. "
    "Do not provide operational code or step-by-step abuse "
    "instructions. "
    "Briefly explain the safety boundary and redirect to a "
    "defensive alternative such as secure coding, detection, "
    "sandboxed analysis, access-control hardening, incident "
    "response, or authorized lab exercises. "
    "Developer request: "
)

_HIGH_RISK_PHRASES = (
    "backdoor",
    "bypass authentication",
    "credential harvester",
    "delete all files",
    "disable antivirus",
    "disable endpoint protection",
    "exfiltrate credentials",
    "keylogger",
    "malware payload",
    "persistence mechanism",
    "ransomware",
    "reverse shell",
    "steal credentials",
    "steal password",
    "unauthorized access",
    "wipe disk",
)


def _is_high_risk_request(
    message: str,
) -> bool:
    normalized = " ".join(
        message.lower().split()
    )

    return any(
        phrase in normalized
        for phrase in _HIGH_RISK_PHRASES
    )


def build_coding_prompt(
    request: AgentDispatchRequest,
) -> str:
    if not isinstance(
        request,
        AgentDispatchRequest,
    ):
        raise AgentRegistryValidationError(
            "Invalid agent dispatch request."
        )

    if _is_high_risk_request(
        request.message
    ):
        prompt = (
            _SAFE_REDIRECT_PROMPT
            + request.message
        )
    else:
        prompt = (
            _CODING_PROMPT_PREFIX
            + request.message
            + _CODING_PROMPT_SUFFIX
        )

    if len(prompt) > MAX_AGENT_MESSAGE_LENGTH:
        raise AgentRegistryValidationError(
            "Coding prompt is too long."
        )

    return prompt


def dispatch_coding(
    request: AgentDispatchRequest,
) -> AgentDispatchResult:
    return AgentDispatchResult(
        agent_id=CODING_AGENT_ID,
        route=CODING_AGENT_ROUTE,
        prompt=build_coding_prompt(
            request
        ),
        sources=(),
    )


def build_coding_agent_definition(
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=CODING_AGENT_ID,
        name="Coding Agent",
        description=(
            "Prepares safe prompts for explaining, "
            "writing, debugging, and reviewing code."
        ),
        capabilities=(
            CODING_AGENT_CAPABILITIES
        ),
        handler=dispatch_coding,
    )
