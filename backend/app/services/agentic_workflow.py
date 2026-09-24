"""Persistent, resumable, deterministic Phase 3B workflow.

Only structured results, triggered rules, and evidence references are stored.
There are no LLM calls and no OTA action executor in this module.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AgenticWorkflow, Campaign, HumanApprovalRequest, Incident, IncidentEvidence,
    OTAEvent, SimulationRun, SimulationStage, SimulationVehicle, SoftwarePackage,
    WorkflowHistory,
)


AGENTS = ("MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION")
NEXT_AGENT = {agent: AGENTS[index + 1] if index + 1 < len(AGENTS) else None for index, agent in enumerate(AGENTS)}
TERMINAL_STATUSES = {"WAITING_FOR_HUMAN_APPROVAL", "HUMAN_APPROVED", "HUMAN_REJECTED", "FAILED"}
ALLOWED_ACTIONS = {
    "PAUSE_CAMPAIGN",
    "EXCLUDE_INCOMPATIBLE_VEHICLES",
    "ASSIGN_CORRECTIVE_PACKAGE",
    "REQUEST_ADDITIONAL_INVESTIGATION",
}


class EvidenceValidationError(ValueError):
    pass


class WorkflowTimeoutError(TimeoutError):
    pass


def workflow_state(workflow: AgenticWorkflow) -> dict:
    return {
        "workflow_id": workflow.id,
        "incident_id": workflow.incident_id,
        "campaign_id": workflow.campaign_id,
        "canary_stage_id": workflow.canary_stage_id,
        "current_agent": workflow.current_agent,
        "workflow_status": workflow.workflow_status,
        "failed_vehicle_ids": workflow.failed_vehicle_ids,
        "successful_vehicle_ids": workflow.successful_vehicle_ids,
        "normalized_errors": workflow.normalized_errors,
        "timeline": workflow.timeline,
        "correlations": workflow.correlations,
        "hypotheses": workflow.hypotheses,
        "evidence_ids": workflow.evidence_ids,
        "confidence_components": workflow.confidence_components,
        "global_confidence": workflow.global_confidence,
        "recommended_actions": workflow.recommended_actions,
        "approval_status": workflow.approval_status,
        "retry_count": workflow.retry_count,
        "last_error": workflow.last_error,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


def create_workflow(db: Session, incident_id: str) -> tuple[AgenticWorkflow, bool]:
    existing = db.scalar(select(AgenticWorkflow).where(AgenticWorkflow.incident_id == incident_id))
    if existing is not None:
        return existing, False
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ValueError("Unknown incident")
    if incident.anomaly_score is not None:
        raise ValueError("Phase 3B requires anomaly_score to remain null")
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == incident.simulation_id,
        SimulationStage.stage_number == incident.stage_number,
    ))
    if stage is None:
        raise ValueError("Incident Canary stage is missing")
    workflow = AgenticWorkflow(
        incident_id=incident.id,
        campaign_id=incident.campaign_id,
        canary_stage_id=stage.id,
        current_agent=AGENTS[0],
        workflow_status="QUEUED",
    )
    db.add(workflow)
    db.flush()
    return workflow, True


def _next_history_sequence(db: Session, workflow_id: str) -> int:
    current = db.scalar(select(func.max(WorkflowHistory.sequence)).where(WorkflowHistory.workflow_id == workflow_id))
    return (current or 0) + 1


def _history(
    db: Session,
    workflow: AgenticWorkflow,
    agent: str,
    event_type: str,
    input_summary: dict,
    output_summary: dict,
    duration_ms: int,
    error: Exception | None = None,
) -> None:
    db.add(WorkflowHistory(
        workflow_id=workflow.id,
        sequence=_next_history_sequence(db, workflow.id),
        agent=agent,
        event_type=event_type,
        input_summary=input_summary,
        output_summary=output_summary,
        duration_ms=duration_ms,
        error_type=type(error).__name__ if error else None,
        error_message=_safe_error(error) if error else None,
    ))


def _safe_error(error: Exception) -> str:
    message = str(error)
    message = re.sub(r"(?i)(api[_-]?key|token|password)\s*[=:]\s*\S+", r"\1=[REDACTED]", message)
    message = re.sub(r"://([^:/\s]+):([^@/\s]+)@", r"://\1:[REDACTED]@", message)
    return message[:1000]


def _input_summary(workflow: AgenticWorkflow) -> dict:
    return {
        "workflow_status": workflow.workflow_status,
        "failed_vehicle_count": len(workflow.failed_vehicle_ids),
        "successful_vehicle_count": len(workflow.successful_vehicle_ids),
        "evidence_count": len(workflow.evidence_ids),
        "correlation_count": len(workflow.correlations),
        "hypothesis_count": len(workflow.hypotheses),
    }


def _output_summary(workflow: AgenticWorkflow) -> dict:
    return {
        "failed_vehicle_count": len(workflow.failed_vehicle_ids),
        "successful_vehicle_count": len(workflow.successful_vehicle_ids),
        "normalized_error_count": len(workflow.normalized_errors),
        "timeline_count": len(workflow.timeline),
        "correlation_count": len(workflow.correlations),
        "hypothesis_count": len(workflow.hypotheses),
        "evidence_count": len(workflow.evidence_ids),
        "recommended_action_count": len(workflow.recommended_actions),
        "global_confidence": workflow.global_confidence,
        "approval_status": workflow.approval_status,
    }


def validate_evidence_ids(db: Session, incident_id: str, evidence_ids: list[str]) -> None:
    if not evidence_ids:
        raise EvidenceValidationError("At least one evidence_id is required")
    existing = set(db.scalars(select(IncidentEvidence.id).where(
        IncidentEvidence.incident_id == incident_id,
        IncidentEvidence.id.in_(set(evidence_ids)),
    )))
    missing = sorted(set(evidence_ids) - existing)
    if missing:
        raise EvidenceValidationError(f"Unknown incident evidence IDs: {missing}")


def validate_hypotheses(db: Session, workflow: AgenticWorkflow) -> None:
    for hypothesis in workflow.hypotheses:
        evidence_ids = hypothesis.get("evidence_ids") or []
        validate_evidence_ids(db, workflow.incident_id, evidence_ids)


def monitoring_agent(db: Session, workflow: AgenticWorkflow) -> None:
    incident = db.get(Incident, workflow.incident_id)
    stage = db.get(SimulationStage, workflow.canary_stage_id)
    if incident is None or stage is None:
        raise ValueError("Incident or Canary stage missing")
    if incident.anomaly_score is not None:
        raise ValueError("Operational Kaggle scores are prohibited in Phase 3B")
    failure_vehicle_ids = set(db.scalars(select(OTAEvent.vehicle_id).where(
        OTAEvent.simulation_id == incident.simulation_id,
        OTAEvent.stage_number == incident.stage_number,
        OTAEvent.event_type == "FAILURE",
    )))
    events = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == incident.simulation_id,
        OTAEvent.stage_number == incident.stage_number,
    ).order_by(OTAEvent.vehicle_id, OTAEvent.sequence)))
    links = {link.event_id: link for link in db.scalars(select(IncidentEvidence).where(
        IncidentEvidence.incident_id == incident.id,
    ))}
    for event in events:
        if event.event_id not in links:
            link = IncidentEvidence(
                incident_id=incident.id,
                event_id=event.event_id,
                evidence_type=("FAILED_VEHICLE_TIMELINE" if event.vehicle_id in failure_vehicle_ids else "SUCCESS_CONTROL_TIMELINE"),
            )
            db.add(link)
            db.flush()
            links[event.event_id] = link
    workflow.evidence_ids = sorted(link.id for link in links.values())
    workflow.failed_vehicle_ids = sorted(failure_vehicle_ids)
    workflow.successful_vehicle_ids = sorted({event.vehicle_id for event in events} - failure_vehicle_ids)


def log_analysis_agent(db: Session, workflow: AgenticWorkflow) -> None:
    rows = list(db.execute(
        select(IncidentEvidence, OTAEvent)
        .join(OTAEvent, OTAEvent.event_id == IncidentEvidence.event_id)
        .where(IncidentEvidence.incident_id == workflow.incident_id)
        .order_by(OTAEvent.vehicle_id, OTAEvent.sequence)
    ))
    if not rows:
        raise EvidenceValidationError("Incident has no associated PostgreSQL evidence")
    by_vehicle: dict[str, list[tuple[IncidentEvidence, OTAEvent]]] = defaultdict(list)
    for link, event in rows:
        by_vehicle[event.vehicle_id].append((link, event))
    timelines = []
    error_groups: dict[tuple[str, str, str], dict] = {}
    failed, successful = [], []
    for vehicle_id, vehicle_rows in sorted(by_vehicle.items()):
        is_failed = any(event.event_type == "FAILURE" for _, event in vehicle_rows)
        (failed if is_failed else successful).append(vehicle_id)
        events = []
        previous_step = None
        for link, event in vehicle_rows:
            normalized_step = event.installation_step.strip().upper()
            normalized_error = event.error_code.strip().upper() if event.error_code else None
            events.append({
                "evidence_id": link.id,
                "event_id": event.event_id,
                "sequence": event.sequence,
                "timestamp": event.timestamp.isoformat(),
                "installation_step": normalized_step,
                "error_code": normalized_error,
                "hardware_revision": event.hardware_revision.strip().upper(),
                "software_version": event.software_version,
                "battery_level": event.battery_level,
                "network_quality": event.network_quality,
                "free_storage_mb": event.free_storage_mb,
            })
            if event.event_type == "FAILURE":
                key = (event.hardware_revision.strip().upper(), normalized_error or "UNKNOWN", previous_step or "UNKNOWN")
                group = error_groups.setdefault(key, {
                    "hardware_revision": key[0], "error_code": key[1],
                    "installation_step": key[2], "vehicle_ids": [], "evidence_ids": [],
                })
                group["vehicle_ids"].append(vehicle_id)
                group["evidence_ids"].append(link.id)
            previous_step = normalized_step
        timelines.append({"vehicle_id": vehicle_id, "outcome": "FAILURE" if is_failed else "SUCCESS", "events": events})
    normalized_errors = []
    for group in error_groups.values():
        group["vehicle_ids"] = sorted(set(group["vehicle_ids"]))
        group["evidence_ids"] = sorted(set(group["evidence_ids"]))
        group["count"] = len(group["vehicle_ids"])
        validate_evidence_ids(db, workflow.incident_id, group["evidence_ids"])
        normalized_errors.append(group)
    workflow.timeline = timelines
    workflow.failed_vehicle_ids = sorted(failed)
    workflow.successful_vehicle_ids = sorted(successful)
    workflow.normalized_errors = sorted(normalized_errors, key=lambda item: (-item["count"], item["error_code"]))
    workflow.evidence_ids = sorted(link.id for link, _ in rows)


def _risk_ratio(a: int, b: int, c: int, d: int) -> tuple[float | None, list[float] | None]:
    if a + b == 0 or c + d == 0:
        return None, None
    aa, bb, cc, dd = (float(a), float(b), float(c), float(d))
    if min(aa, bb, cc, dd) == 0:
        aa, bb, cc, dd = aa + 0.5, bb + 0.5, cc + 0.5, dd + 0.5
    exposed_rate = aa / (aa + bb)
    reference_rate = cc / (cc + dd)
    rr = exposed_rate / reference_rate if reference_rate else None
    if rr is None:
        return None, None
    standard_error = math.sqrt((1 / aa) - (1 / (aa + bb)) + (1 / cc) - (1 / (cc + dd)))
    interval = [math.exp(math.log(rr) - 1.96 * standard_error), math.exp(math.log(rr) + 1.96 * standard_error)]
    return rr, interval


def correlation_agent(db: Session, workflow: AgenticWorkflow) -> None:
    if not workflow.timeline:
        raise ValueError("Log Analysis must complete before correlation")
    incident = db.get(Incident, workflow.incident_id)
    campaign = db.get(Campaign, workflow.campaign_id)
    package = db.get(SoftwarePackage, campaign.software_package_id)
    vehicle_facts = []
    for timeline in workflow.timeline:
        first = timeline["events"][0]
        failure_event = next((event for event in timeline["events"] if event["error_code"]), None)
        terminal = timeline["events"][-1]
        vehicle_facts.append({
            "vehicle_id": timeline["vehicle_id"],
            "failed": timeline["outcome"] == "FAILURE",
            "hardware_revision": first["hardware_revision"],
            "software_version": first["software_version"],
            "package": f"{package.name}:{package.version}",
            "error_code": failure_event["error_code"] if failure_event else "NONE",
            "installation_step": (
                next((group["installation_step"] for group in workflow.normalized_errors if timeline["vehicle_id"] in group["vehicle_ids"]), "SUCCESS")
            ),
            "battery_level": first["battery_level"],
            "network_quality": first["network_quality"],
            "free_storage_mb": first["free_storage_mb"],
            "evidence_id": (failure_event or terminal)["evidence_id"],
        })
    total_failures = sum(fact["failed"] for fact in vehicle_facts)
    correlations = []
    for factor in ("hardware_revision", "software_version", "package", "error_code", "installation_step"):
        levels = sorted({fact[factor] for fact in vehicle_facts})
        for level in levels:
            exposed = [fact for fact in vehicle_facts if fact[factor] == level]
            reference = [fact for fact in vehicle_facts if fact[factor] != level]
            a = sum(fact["failed"] for fact in exposed)
            b = len(exposed) - a
            c = sum(fact["failed"] for fact in reference)
            d = len(reference) - c
            rr, interval = _risk_ratio(a, b, c, d)
            correlations.append({
                "factor": factor, "level": str(level), "exposed_count": len(exposed),
                "failures": a, "successes": b, "failure_rate": a / len(exposed),
                "risk_ratio": rr, "confidence_interval_95": interval,
                "outcome_signature": factor in {"error_code", "installation_step"},
                "evidence_ids": sorted({fact["evidence_id"] for fact in exposed}),
                "correlation_is_not_causation": True,
            })
    numeric_rules = (
        ("battery_level", "LT_20", lambda value: value < 20),
        ("network_quality", "LT_50", lambda value: value < 50),
        ("free_storage_mb", "LT_1024", lambda value: value < 1024),
    )
    numeric_summary = {}
    for factor, level, predicate in numeric_rules:
        exposed = [fact for fact in vehicle_facts if predicate(fact[factor])]
        reference = [fact for fact in vehicle_facts if not predicate(fact[factor])]
        a, b = sum(fact["failed"] for fact in exposed), sum(not fact["failed"] for fact in exposed)
        c, d = sum(fact["failed"] for fact in reference), sum(not fact["failed"] for fact in reference)
        rr, interval = _risk_ratio(a, b, c, d)
        correlations.append({
            "factor": factor, "level": level, "exposed_count": len(exposed),
            "failures": a, "successes": b,
            "failure_rate": a / len(exposed) if exposed else 0.0,
            "risk_ratio": rr, "confidence_interval_95": interval,
            "outcome_signature": False,
            "evidence_ids": sorted({fact["evidence_id"] for fact in exposed}),
            "correlation_is_not_causation": True,
        })
        numeric_summary[factor] = {
            "failed_mean": sum(fact[factor] for fact in vehicle_facts if fact["failed"]) / total_failures,
            "successful_mean": sum(fact[factor] for fact in vehicle_facts if not fact["failed"]) / (len(vehicle_facts) - total_failures),
        }
    for item in correlations:
        if item["evidence_ids"]:
            validate_evidence_ids(db, workflow.incident_id, item["evidence_ids"])
    correlations.append({
        "factor": "numeric_summary", "level": "MEANS_BY_OUTCOME",
        "values": numeric_summary, "evidence_ids": workflow.evidence_ids,
        "correlation_is_not_causation": True,
    })
    workflow.correlations = correlations


def _score_hypothesis(association: float, support: float, error_consistency: float, step_consistency: float, coverage: float) -> tuple[dict, float]:
    components = {
        "association_strength": round(max(0.0, min(1.0, association)), 6),
        "failure_support": round(max(0.0, min(1.0, support)), 6),
        "error_consistency": round(max(0.0, min(1.0, error_consistency)), 6),
        "step_consistency": round(max(0.0, min(1.0, step_consistency)), 6),
        "evidence_coverage": round(max(0.0, min(1.0, coverage)), 6),
    }
    score = (
        0.35 * components["association_strength"]
        + 0.20 * components["failure_support"]
        + 0.20 * components["error_consistency"]
        + 0.15 * components["step_consistency"]
        + 0.10 * components["evidence_coverage"]
    )
    return components, round(score, 6)


def rca_agent(db: Session, workflow: AgenticWorkflow) -> None:
    if not workflow.correlations or not workflow.normalized_errors:
        raise ValueError("Correlation and normalized errors are required")
    failed_count = len(workflow.failed_vehicle_ids)
    top_error = max(workflow.normalized_errors, key=lambda item: item["count"])
    campaign = db.get(Campaign, workflow.campaign_id)
    package = db.get(SoftwarePackage, campaign.software_package_id)
    # Outcome signatures strengthen hypotheses but are not causal candidates.
    candidates = [
        item for item in workflow.correlations
        if item.get("failures", 0)
        and item.get("evidence_ids")
        and not item.get("outcome_signature", False)
        and item.get("risk_ratio") is not None
        and item["risk_ratio"] > 1.0
    ]
    hypotheses = []
    for correlation in candidates:
        rr = correlation.get("risk_ratio")
        association = min(1.0, math.log2(max(rr or 1.0, 1.0)) / 4) if rr else 0.0
        support = correlation["failures"] / failed_count if failed_count else 0.0
        signature_matches = correlation["factor"] in {"error_code", "installation_step"}
        error_consistency = top_error["count"] / failed_count if signature_matches or correlation["factor"] == "hardware_revision" else 0.0
        step_consistency = top_error["count"] / failed_count if correlation["factor"] in {"hardware_revision", "installation_step"} else 0.0
        evidence_ids = sorted(set(correlation["evidence_ids"] + (top_error["evidence_ids"] if correlation["factor"] == "hardware_revision" else [])))
        components, score = _score_hypothesis(
            association, support, error_consistency, step_consistency,
            len(evidence_ids) / max(1, correlation["exposed_count"]),
        )
        if correlation["factor"] == "hardware_revision":
            statement = (
                f"Observed {correlation['factor']}={correlation['level']} with package "
                f"{package.name}:{package.version} is associated with failures; dominant signature is "
                f"{top_error['error_code']} at {top_error['installation_step']}."
            )
        else:
            statement = (
                f"Observed {correlation['factor']}={correlation['level']} is associated with failures; "
                "the small exposed cohort requires independent causal validation."
            )
        hypothesis = {
            "hypothesis_id": str(uuid4()),
            "rule_id": "STRATIFIED_FAILURE_SIGNATURE_V1",
            "factor": correlation["factor"],
            "level": correlation["level"],
            "statement": statement,
            "score_components": components,
            "confidence": score,
            "evidence_ids": evidence_ids,
            "correlation_is_not_causation": True,
        }
        validate_evidence_ids(db, workflow.incident_id, evidence_ids)
        hypotheses.append(hypothesis)
    hypotheses.sort(key=lambda item: (-item["confidence"], item["factor"], item["level"]))
    hypotheses = hypotheses[:8]
    for rank, hypothesis in enumerate(hypotheses, 1):
        hypothesis["rank"] = rank
    if not hypotheses:
        raise EvidenceValidationError("No evidence-backed hypothesis could be created")
    workflow.hypotheses = hypotheses
    workflow.confidence_components = hypotheses[0]["score_components"]
    workflow.global_confidence = hypotheses[0]["confidence"]
    validate_hypotheses(db, workflow)


def decision_agent(db: Session, workflow: AgenticWorkflow) -> None:
    validate_hypotheses(db, workflow)
    top = workflow.hypotheses[0]
    actions = []

    def propose(action: str, reason: str) -> None:
        if action not in ALLOWED_ACTIONS:
            raise ValueError("Action is not allowed by Phase 3B policy")
        actions.append({
            "action": action,
            "status": "PROPOSED",
            "requires_human_approval": True,
            "reason": reason,
            "hypothesis_id": top["hypothesis_id"],
            "evidence_ids": top["evidence_ids"],
            "executed": False,
        })

    if (workflow.global_confidence or 0) >= 0.5:
        propose("PAUSE_CAMPAIGN", "Failure threshold and evidence-backed hypothesis require human review.")
    if top["factor"] == "hardware_revision":
        propose("EXCLUDE_INCOMPATIBLE_VEHICLES", f"Review exclusion for observed cohort {top['level']}.")
        propose("ASSIGN_CORRECTIVE_PACKAGE", "Validate package compatibility in a separate controlled process.")
    propose("REQUEST_ADDITIONAL_INVESTIGATION", "Correlation does not prove causality; request independent validation.")
    approval = db.scalar(select(HumanApprovalRequest).where(HumanApprovalRequest.workflow_id == workflow.id))
    if approval is None:
        db.add(HumanApprovalRequest(workflow_id=workflow.id, status="PENDING"))
    workflow.recommended_actions = actions
    workflow.approval_status = "PENDING"


DEFAULT_RUNNERS: dict[str, Callable[[Session, AgenticWorkflow], None]] = {
    "MONITORING": monitoring_agent,
    "LOG_ANALYSIS": log_analysis_agent,
    "CORRELATION": correlation_agent,
    "RCA": rca_agent,
    "DECISION": decision_agent,
}


def run_workflow(
    db: Session,
    workflow_id: str,
    runners: dict[str, Callable[[Session, AgenticWorkflow], None]] | None = None,
    max_transitions: int = len(AGENTS),
) -> AgenticWorkflow:
    active_runners = {**DEFAULT_RUNNERS, **(runners or {})}
    transitions = 0
    while transitions < max_transitions:
        workflow = db.scalar(select(AgenticWorkflow).where(AgenticWorkflow.id == workflow_id).with_for_update())
        if workflow is None:
            raise ValueError("Unknown workflow")
        if workflow.workflow_status in TERMINAL_STATUSES:
            return workflow
        if workflow.workflow_status == "RETRYABLE_ERROR":
            return workflow
        agent = workflow.current_agent
        if agent not in AGENTS:
            raise ValueError("Invalid workflow agent")
        input_summary = _input_summary(workflow)
        workflow.workflow_status = "RUNNING"
        started = time.perf_counter()
        try:
            active_runners[agent](db, workflow)
            if agent in {"LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION"}:
                if workflow.evidence_ids:
                    validate_evidence_ids(db, workflow.incident_id, workflow.evidence_ids)
            duration_ms = max(0, round((time.perf_counter() - started) * 1000))
            if duration_ms > workflow.agent_timeout_seconds * 1000:
                raise WorkflowTimeoutError(f"{agent} exceeded {workflow.agent_timeout_seconds}s timeout")
            next_agent = NEXT_AGENT[agent]
            workflow.current_agent = next_agent
            workflow.workflow_status = "WAITING_FOR_HUMAN_APPROVAL" if next_agent is None else "QUEUED"
            workflow.last_error = None
            _history(db, workflow, agent, "AGENT_COMPLETED", input_summary, _output_summary(workflow), duration_ms)
            db.commit()
            transitions += 1
        except Exception as error:
            db.rollback()
            workflow = db.get(AgenticWorkflow, workflow_id)
            workflow.retry_count += 1
            workflow.last_error = _safe_error(error)
            workflow.workflow_status = "FAILED" if workflow.retry_count >= workflow.max_retries else "RETRYABLE_ERROR"
            duration_ms = max(0, round((time.perf_counter() - started) * 1000))
            _history(db, workflow, agent, "AGENT_ERROR", input_summary, {}, duration_ms, error)
            db.commit()
            return workflow
    workflow = db.get(AgenticWorkflow, workflow_id)
    if workflow.workflow_status not in TERMINAL_STATUSES and workflow.workflow_status != "RETRYABLE_ERROR":
        workflow.retry_count += 1
        workflow.last_error = "Maximum transition count reached"
        workflow.workflow_status = "FAILED" if workflow.retry_count >= workflow.max_retries else "RETRYABLE_ERROR"
        _history(db, workflow, workflow.current_agent or "ORCHESTRATOR", "LOOP_GUARD", {}, {}, 0)
        db.commit()
    return workflow


def prepare_retry(db: Session, workflow_id: str) -> AgenticWorkflow:
    workflow = db.get(AgenticWorkflow, workflow_id)
    if workflow is None:
        raise ValueError("Unknown workflow")
    if workflow.workflow_status != "RETRYABLE_ERROR":
        raise ValueError("Workflow is not retryable")
    if workflow.retry_count >= workflow.max_retries:
        raise ValueError("Retry limit reached")
    workflow.workflow_status = "QUEUED"
    workflow.last_error = None
    db.commit()
    return workflow


def record_human_decision(
    db: Session,
    workflow_id: str,
    approved: bool,
    user: str,
    timestamp: datetime,
    comment: str,
) -> AgenticWorkflow:
    workflow = db.get(AgenticWorkflow, workflow_id)
    if workflow is None:
        raise ValueError("Unknown workflow")
    approval = db.scalar(select(HumanApprovalRequest).where(HumanApprovalRequest.workflow_id == workflow_id))
    if approval is None or workflow.workflow_status != "WAITING_FOR_HUMAN_APPROVAL":
        if approval is not None and approval.status in {"APPROVED", "REJECTED"}:
            requested = "APPROVED" if approved else "REJECTED"
            if approval.status == requested and approval.decided_by == user and approval.comment == comment:
                return workflow
        raise ValueError("Workflow is not waiting for human approval")
    if timestamp.tzinfo is None:
        raise ValueError("Human decision timestamp must include a timezone")
    approval.status = "APPROVED" if approved else "REJECTED"
    approval.decided_at = timestamp.astimezone(timezone.utc)
    approval.decided_by = user
    approval.comment = comment
    workflow.approval_status = approval.status
    workflow.workflow_status = "HUMAN_APPROVED" if approved else "HUMAN_REJECTED"
    _history(
        db, workflow, "HUMAN", "HUMAN_DECISION",
        {"user": user}, {"decision": approval.status, "comment": comment, "ota_actions_executed": 0}, 0,
    )
    db.commit()
    return workflow
