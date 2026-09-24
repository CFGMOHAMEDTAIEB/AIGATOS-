from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.schemas.agents import ToolInputPayload, ToolInvocation, ToolOutputPayload


class ToolAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    allowed_agents: frozenset[str]
    mode: str = "READ_ONLY"
    timeout_seconds: int = 15
    input_model: type[BaseModel] = ToolInputPayload
    output_model: type[BaseModel] = ToolOutputPayload


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "calculate_failure_rate": ToolDefinition("calculate_failure_rate", frozenset({"MONITORING"})),
    "evaluate_threshold": ToolDefinition("evaluate_threshold", frozenset({"MONITORING"})),
    "find_or_create_incident": ToolDefinition("find_or_create_incident", frozenset({"MONITORING"}), "INTERNAL_WRITE"),
    "get_vehicle_timeline": ToolDefinition("get_vehicle_timeline", frozenset({"LOG_ANALYSIS"})),
    "normalize_error": ToolDefinition("normalize_error", frozenset({"LOG_ANALYSIS"})),
    "group_error_signatures": ToolDefinition("group_error_signatures", frozenset({"LOG_ANALYSIS"})),
    "identify_failure_step": ToolDefinition("identify_failure_step", frozenset({"LOG_ANALYSIS"})),
    "build_cohorts": ToolDefinition("build_cohorts", frozenset({"CORRELATION"})),
    "calculate_risk_ratio": ToolDefinition("calculate_risk_ratio", frozenset({"CORRELATION"})),
    "calculate_confidence_interval": ToolDefinition("calculate_confidence_interval", frozenset({"CORRELATION"})),
    "evaluate_support": ToolDefinition("evaluate_support", frozenset({"CORRELATION"})),
    "get_previous_agent_results": ToolDefinition("get_previous_agent_results", frozenset({"RCA"})),
    "validate_evidence_ids": ToolDefinition("validate_evidence_ids", frozenset({"RCA"})),
    "apply_known_error_rules": ToolDefinition("apply_known_error_rules", frozenset({"RCA"})),
    "rank_root_causes": ToolDefinition("rank_root_causes", frozenset({"RCA"})),
    "list_allowed_recommendations": ToolDefinition("list_allowed_recommendations", frozenset({"DECISION"})),
    "validate_safety_policy": ToolDefinition("validate_safety_policy", frozenset({"DECISION"})),
    "propose_recommendation": ToolDefinition("propose_recommendation", frozenset({"DECISION"})),
    "create_human_approval_request": ToolDefinition("create_human_approval_request", frozenset({"DECISION"}), "INTERNAL_WRITE"),
}


AGENT_TOOLS: dict[str, tuple[str, ...]] = {
    agent: tuple(name for name, definition in TOOL_REGISTRY.items() if agent in definition.allowed_agents)
    for agent in ("MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION")
}


def authorize_tool(invocation: ToolInvocation) -> ToolDefinition:
    definition = TOOL_REGISTRY.get(invocation.tool_name)
    if definition is None:
        raise ToolAuthorizationError(f"Unknown tool: {invocation.tool_name}")
    if invocation.agent_type not in definition.allowed_agents:
        raise ToolAuthorizationError(
            f"Agent {invocation.agent_type} is not authorized to use {invocation.tool_name}"
        )
    if definition.mode not in {"READ_ONLY", "INTERNAL_WRITE"}:
        raise ToolAuthorizationError(f"Tool {invocation.tool_name} has a prohibited mode")
    definition.input_model.model_validate(invocation.input_payload)
    return definition
