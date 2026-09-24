"""Read-only LLM translator for live-simulation configuration drafts."""

from __future__ import annotations

import json

from app.llm_config import LLMConfigurationError, load_llm_settings, redact_secrets
from app.llm_providers import LLMError, get_provider
from app.schemas.live import CANARY_STRATEGIES, PACKAGE_TYPES, SCENARIO_RULES, LiveSimulationDraft


class ConfigurationAssistantError(ValueError):
    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message);self.detail=detail


SYSTEM_PROMPT = """You translate a user's OTA simulation description into one JSON object only.
This is a draft operation: never claim that anything was created, executed, approved, or written.
Use exactly these scenario keys and their fixed error/step pairs: {scenario_rules}.
Allowed hardware: ANY, HW_REV_A, HW_REV_B. Allowed package types: {package_types}.
Allowed Canary strategies: {canary_strategies}. Probabilities are numbers from 0 to 1.
Return keys: created_by, seed, campaign, fleet, injections. Each injection uses exactly one of
affected_count or affected_percentage. HW_REV_A + HW_REV_B must equal vehicle_count.
Use conservative defaults for details the user omitted, but do not invent extra failure rules.
"""


def _json_object(content: str) -> dict:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1])
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigurationAssistantError("Le fournisseur LLM n'a pas renvoyé un JSON valide.") from error
    if not isinstance(decoded, dict):
        raise ConfigurationAssistantError("Le fournisseur LLM doit renvoyer un objet JSON.")
    return decoded


def generate_configuration_draft(prompt: str) -> tuple[LiveSimulationDraft, dict]:
    """Generate and deterministically validate a draft. This function has no database access."""
    try:
        settings = load_llm_settings()
    except (ValueError, LLMConfigurationError) as error:
        raise ConfigurationAssistantError(redact_secrets(str(error))) from error
    if not settings.configured:
        raise ConfigurationAssistantError(
            "L'assistant LLM n'est pas configuré. La configuration manuelle reste disponible."
        )
    system = SYSTEM_PROMPT.format(
        scenario_rules=json.dumps(SCENARIO_RULES, sort_keys=True),
        package_types=", ".join(sorted(PACKAGE_TYPES)),
        canary_strategies=", ".join(sorted(CANARY_STRATEGIES)),
    )
    try:
        result, draft = get_provider(settings).generate_structured(system, prompt, LiveSimulationDraft)
    except LLMError as error:
        raise ConfigurationAssistantError(error.message, error.public()) from error
    except Exception as error:
        raise ConfigurationAssistantError(
            "Une erreur interne sûre a interrompu l'assistant LLM.",
            {"code": "LLM_INTERNAL_ERROR", "message": "Une erreur interne sûre a interrompu l'assistant LLM.",
             "provider": settings.provider, "model": settings.model, "retryable": False},
        ) from error
    return draft, {
        "provider": settings.provider,
        "model": settings.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "attempt_count": result.attempt_count,
        "writes_performed": 0,
        "actions_executed": 0,
    }
