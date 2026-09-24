from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.schemas.agents import ToolInputPayload, ToolInvocation, ToolOutputPayload
from sqlalchemy import select


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
    "read_simulation_metrics": ToolDefinition("read_simulation_metrics", frozenset({"MONITORING"})),
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
    "read_agent_outputs": ToolDefinition("read_agent_outputs", frozenset({"RCA"})),
    "validate_evidence_ids": ToolDefinition("validate_evidence_ids", frozenset({"RCA"})),
    "apply_known_error_rules": ToolDefinition("apply_known_error_rules", frozenset({"RCA"})),
    "rank_root_causes": ToolDefinition("rank_root_causes", frozenset({"RCA"})),
    "list_allowed_recommendations": ToolDefinition("list_allowed_recommendations", frozenset({"DECISION"})),
    "validate_safety_policy": ToolDefinition("validate_safety_policy", frozenset({"DECISION"})),
    "propose_recommendation": ToolDefinition("propose_recommendation", frozenset({"DECISION"})),
    "create_human_approval_request": ToolDefinition("create_human_approval_request", frozenset({"DECISION"}), "INTERNAL_WRITE"),
    "create_pending_approval": ToolDefinition("create_pending_approval", frozenset({"DECISION"}), "INTERNAL_WRITE"),
}


AGENT_TOOLS: dict[str, tuple[str, ...]] = {
    agent: tuple(name for name, definition in TOOL_REGISTRY.items() if agent in definition.allowed_agents)
    for agent in ("MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION")
}

PRIMARY_STAGE_TOOLS = {
    "MONITORING": "read_simulation_metrics",
    "LOG_ANALYSIS": "get_vehicle_timeline",
    "CORRELATION": "build_cohorts",
    "RCA": "rank_root_causes",
    "DECISION": "create_pending_approval",
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


def execute_stage_tool(
    invocation: ToolInvocation,
    db,
    workflow,
    stage_handler,
) -> tuple[ToolDefinition, dict]:
    """Execute a registered primary tool through its bounded domain handler.

    The handler is selected by the orchestrator, never by model-provided code. Its
    database scope is the already-authorized incident/workflow, and it cannot
    reach Celery or any OTA executor. Returning only after the handler completes
    lets the caller persist the actual result as the tool-call output.
    """
    definition = authorize_tool(invocation)
    if invocation.tool_name not in AGENT_TOOLS[invocation.agent_type]:
        raise ToolAuthorizationError("The requested tool is outside this agent's allowlist")
    stage_handler(db, workflow)
    return definition, _execute_business_tool(db, workflow, invocation)


def _execute_business_tool(db, workflow, invocation: ToolInvocation) -> dict:
    """Run a deterministic, read-bounded implementation for an allowed tool."""
    from app.models import (
        AgentExecution, HumanApprovalRequest, Incident, SimulationStage,
    )

    name = invocation.tool_name
    if name in {"read_simulation_metrics", "calculate_failure_rate", "evaluate_threshold"}:
        incident = db.get(Incident, workflow.incident_id)
        stage = db.get(SimulationStage, workflow.canary_stage_id)
        if incident is None or stage is None:
            raise ToolAuthorizationError("Simulation metrics are unavailable")
        rate = stage.failure_count / stage.vehicle_count if stage.vehicle_count else 0.0
        threshold = incident.threshold
        if name == "read_simulation_metrics":
            return {"vehicle_count": stage.vehicle_count, "success_count": stage.success_count,
                    "failure_count": stage.failure_count, "failure_rate": rate}
        if name == "calculate_failure_rate":
            return {"failure_count": stage.failure_count, "vehicle_count": stage.vehicle_count,
                    "failure_rate": rate}
        return {"failure_rate": rate, "threshold": threshold,
                "threshold_reached": rate >= threshold}
    if name == "find_or_create_incident":
        incident = db.get(Incident, workflow.incident_id)
        if incident is None:
            raise ToolAuthorizationError("The workflow incident does not exist")
        return {"incident_id": incident.id, "created": False, "idempotent_match": True}
    if name in {"get_vehicle_timeline", "normalize_error", "group_error_signatures", "identify_failure_step"}:
        timelines = workflow.timeline
        errors = workflow.normalized_errors
        if name == "get_vehicle_timeline":
            return {"vehicle_count": len(timelines),
                    "event_count": sum(len(item.get("events", [])) for item in timelines),
                    "evidence_count": len(workflow.evidence_ids)}
        if name == "normalize_error":
            return {"normalized_error_count": len(errors),
                    "error_codes": sorted({item.get("error_code", "UNKNOWN") for item in errors})}
        if name == "group_error_signatures":
            return {"signature_count": len(errors),
                    "vehicle_count": sum(item.get("count", 0) for item in errors)}
        top = max(errors, key=lambda item: item.get("count", 0), default={})
        return {"failure_step": top.get("installation_step"),
                "error_code": top.get("error_code"), "affected_count": top.get("count", 0)}
    if name in {"build_cohorts", "calculate_risk_ratio", "calculate_confidence_interval", "evaluate_support"}:
        correlations = workflow.correlations
        if name == "build_cohorts":
            return {"cohort_count": len(correlations),
                    "factors": sorted({item.get("factor", "unknown") for item in correlations})}
        if name == "calculate_risk_ratio":
            return {"risk_ratios": [{"factor": item.get("factor"), "level": item.get("level"),
                    "risk_ratio": item.get("risk_ratio")} for item in correlations
                    if item.get("risk_ratio") is not None]}
        if name == "calculate_confidence_interval":
            return {"intervals": [{"factor": item.get("factor"), "level": item.get("level"),
                    "confidence_interval_95": item.get("confidence_interval_95")} for item in correlations
                    if item.get("confidence_interval_95") is not None]}
        return {"supported_cohort_count": sum(bool(item.get("evidence_ids")) for item in correlations),
                "correlation_count": len(correlations)}
    if name in {"get_previous_agent_results", "read_agent_outputs"}:
        rows = list(db.scalars(select(AgentExecution).where(
            AgentExecution.workflow_id == workflow.id,
            AgentExecution.status == "COMPLETED",
            AgentExecution.agent_type != invocation.agent_type,
        ).order_by(AgentExecution.created_at)))
        return {"agent_count": len(rows), "agents": [row.agent_type for row in rows],
                "evidence_count": sum(len(row.evidence_ids) for row in rows)}
    if name == "validate_evidence_ids":
        from app.services.agentic_workflow import validate_evidence_ids
        validate_evidence_ids(db, workflow.incident_id, workflow.evidence_ids)
        return {"valid": True, "evidence_count": len(workflow.evidence_ids)}
    if name == "apply_known_error_rules":
        return {"matched_signatures": [
            {"error_code": item.get("error_code"), "installation_step": item.get("installation_step"),
             "evidence_count": len(item.get("evidence_ids", []))}
            for item in workflow.normalized_errors
        ], "causality_claimed": False}
    if name == "rank_root_causes":
        return {"hypothesis_count": len(workflow.hypotheses),
                "ranked_hypothesis_ids": [item.get("hypothesis_id") for item in workflow.hypotheses],
                "top_confidence": workflow.global_confidence}
    if name == "list_allowed_recommendations":
        from app.services.agentic_workflow import ALLOWED_ACTIONS
        return {"allowed_actions": sorted(ALLOWED_ACTIONS)}
    if name == "validate_safety_policy":
        unsafe = [item for item in workflow.recommended_actions
                  if item.get("action") not in {
                      "PAUSE_CAMPAIGN", "EXCLUDE_INCOMPATIBLE_VEHICLES",
                      "ASSIGN_CORRECTIVE_PACKAGE", "REQUEST_ADDITIONAL_INVESTIGATION",
                  } or item.get("executed")]
        return {"valid": not unsafe, "unsafe_count": len(unsafe),
                "approval_status": workflow.approval_status}
    if name == "propose_recommendation":
        return {"recommendation_count": len(workflow.recommended_actions),
                "all_proposed": all(item.get("status") == "PROPOSED" for item in workflow.recommended_actions),
                "executed_count": sum(bool(item.get("executed")) for item in workflow.recommended_actions)}
    if name in {"create_human_approval_request", "create_pending_approval"}:
        approval = db.scalar(select(HumanApprovalRequest).where(
            HumanApprovalRequest.workflow_id == workflow.id,
        ))
        if approval is None or approval.status != "PENDING":
            raise ToolAuthorizationError("Pending human approval was not persisted")
        return {"approval_request_id": approval.id, "approval_status": approval.status,
                "ota_action_executed": False}
    raise ToolAuthorizationError(f"No implementation registered for {name}")
