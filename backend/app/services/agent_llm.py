from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm_config import LLMConfigurationError, load_llm_settings
from app.llm_providers import LLMError, get_provider


class AgentNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1200)
    cited_evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_limitations(self) -> "AgentNarrative":
        if not self.limitations:
            raise ValueError("At least one limitation is required")
        return self


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_tool: str = Field(min_length=1, max_length=100)
    operational_summary: str = Field(min_length=1, max_length=500)
    expected_result: str = Field(min_length=1, max_length=300)


@dataclass(frozen=True)
class AgentLLMResult:
    source: str
    working_memory: dict
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None


def _enabled() -> bool:
    return os.getenv("AGENT_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def optional_agent_narrative(
    agent: str,
    objective: str,
    deterministic_output: dict,
    evidence_ids: list[str],
) -> AgentLLMResult:
    if agent not in {"LOG_ANALYSIS", "RCA", "DECISION"} or not _enabled():
        return AgentLLMResult("DETERMINISTIC_FALLBACK", {})
    try:
        settings = load_llm_settings()
        if not settings.configured:
            return AgentLLMResult("DETERMINISTIC_FALLBACK", {}, settings.provider, settings.model, "LLM_NOT_CONFIGURED")
        allowed_evidence = evidence_ids[:50]
        system_prompt = (
            "You are an internal explanation helper, not an autonomous agent. "
            "Summarize only the supplied deterministic result. Never invent facts or evidence IDs. "
            "Do not propose an action, change a score, approve a decision, or select a transition."
        )
        user_prompt = json.dumps({
            "agent": agent,
            "objective": objective,
            "deterministic_output": deterministic_output,
            "allowed_evidence_ids": allowed_evidence,
        }, ensure_ascii=False)
        provider_result, narrative = get_provider(settings).generate_structured(
            system_prompt, user_prompt, AgentNarrative,
        )
        if not set(narrative.cited_evidence_ids).issubset(set(allowed_evidence)):
            return AgentLLMResult(
                "DETERMINISTIC_FALLBACK", {}, settings.provider, settings.model,
                "LLM_EVIDENCE_VALIDATION_FAILED",
            )
        return AgentLLMResult(
            "LLM_AUGMENTED",
            {"narrative": narrative.model_dump(), "attempt_count": provider_result.attempt_count},
            settings.provider,
            settings.model,
        )
    except LLMError as error:
        return AgentLLMResult("DETERMINISTIC_FALLBACK", {}, error.provider, error.model, error.code)
    except LLMConfigurationError:
        return AgentLLMResult("DETERMINISTIC_FALLBACK", {}, error_code="LLM_CONFIGURATION_ERROR")


def choose_agent_tool(
    agent: str,
    objective: str,
    observation: dict,
    allowed_tools: list[str],
    deterministic_tool: str,
) -> tuple[dict, str, str | None, str | None, str | None]:
    fallback = {
        "selected_tool": deterministic_tool,
        "operational_summary": f"Analyse déterministe de l’étape {agent} à partir des résultats observés.",
        "expected_result": "Résultat structuré validé avant la transition suivante.",
    }
    if not _enabled():
        return fallback, "DETERMINISTIC_FALLBACK", None, None, None
    try:
        settings = load_llm_settings()
        if not settings.configured:
            return fallback, "DETERMINISTIC_FALLBACK", settings.provider, settings.model, "LLM_NOT_CONFIGURED"
        system = (
            "Select exactly one tool from the allowed list for this bounded analysis step. "
            "Return a brief operational summary, not private chain-of-thought. "
            "Never invent data, call tools, change evidence or scores, approve, or choose a transition."
        )
        user = json.dumps({
            "agent": agent,
            "objective": objective,
            "observation": observation,
            "allowed_tools": allowed_tools,
            "allowed_evidence_ids": observation.get("evidence_ids", [])[:50],
        }, ensure_ascii=False)
        _, plan = get_provider(settings).generate_structured(system, user, AgentPlan)
        if plan.selected_tool not in allowed_tools:
            return fallback, "DETERMINISTIC_FALLBACK", settings.provider, settings.model, "LLM_TOOL_NOT_ALLOWED"
        return plan.model_dump(), "LLM", settings.provider, settings.model, None
    except LLMError as error:
        return fallback, "DETERMINISTIC_FALLBACK", error.provider, error.model, error.code
    except LLMConfigurationError:
        return fallback, "DETERMINISTIC_FALLBACK", None, None, "LLM_CONFIGURATION_ERROR"
