from __future__ import annotations

from app.agents.registry import (
    MAX_AGENT_MESSAGE_LENGTH,
    AgentDefinition,
    AgentDispatchRequest,
    AgentDispatchResult,
    AgentRegistryValidationError,
)


MARKET_RESEARCH_AGENT_ID = "market-research"
MARKET_RESEARCH_AGENT_ROUTE = "market-research"
MARKET_RESEARCH_AGENT_CAPABILITIES = (
    "market-research.compare",
    "market-research.plan",
    "market-research.summarize",
    "market-research.verify",
)

_MARKET_RESEARCH_PROMPT_PREFIX = (
    "You are Onkar AI's Market Research Agent. "
    "Prepare a careful research plan or source-grounded analysis "
    "without pretending that current data has already been fetched. "
    "Research request: "
)

_MARKET_RESEARCH_PROMPT_SUFFIX = (
    " Research rules: "
    "Preserve every user-provided market, product, company, "
    "industry, geography, date range, budget, comparison criterion, "
    "risk constraint, and requested output format exactly. "
    "First identify whether the task is comparison, planning, "
    "summarization, or verification. "
    "For any time-sensitive claim, require fresh verification using "
    "dated and attributable sources before presenting it as current. "
    "Clearly distinguish verified facts, estimates, assumptions, "
    "and inferences. "
    "Never invent prices, market sizes, growth rates, statistics, "
    "citations, source titles, publication dates, benchmarks, "
    "company status, product availability, or current news. "
    "When evidence is missing, say what must be verified instead of "
    "guessing. "
    "Compare sources when they disagree and explain the uncertainty. "
    "Do not provide personalized financial advice, guaranteed "
    "returns, trade signals, or unsupported buy or sell "
    "recommendations. "
    "Do not claim that web research, price checks, news retrieval, "
    "or source verification was completed unless a separate "
    "authorized research tool actually completed it. "
    "Return a structured research-ready prompt or analysis only."
)


def build_market_research_prompt(
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
        _MARKET_RESEARCH_PROMPT_PREFIX
        + request.message
        + _MARKET_RESEARCH_PROMPT_SUFFIX
    )

    if len(prompt) > MAX_AGENT_MESSAGE_LENGTH:
        raise AgentRegistryValidationError(
            "Market Research prompt is too long."
        )

    return prompt


def dispatch_market_research(
    request: AgentDispatchRequest,
) -> AgentDispatchResult:
    return AgentDispatchResult(
        agent_id=MARKET_RESEARCH_AGENT_ID,
        route=MARKET_RESEARCH_AGENT_ROUTE,
        prompt=build_market_research_prompt(
            request
        ),
        sources=(),
    )


def build_market_research_agent_definition(
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=MARKET_RESEARCH_AGENT_ID,
        name="Market Research Agent",
        description=(
            "Prepares safe prompts for market comparison, "
            "planning, summarization, and verification."
        ),
        capabilities=(
            MARKET_RESEARCH_AGENT_CAPABILITIES
        ),
        handler=dispatch_market_research,
    )
