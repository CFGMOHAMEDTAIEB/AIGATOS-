"""Read-only PostgreSQL invariant check for the historical and live jury runs."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    AgenticWorkflow, AuditLog, Campaign, HumanApprovalRequest, Incident,
    IncidentEvidence, LiveSimulationSession, SimulationRun, SimulationStage,
    WorkflowHistory,
)


HISTORICAL_WORKFLOW_ID = "cde0930e-b80a-447f-8ccc-92c6d97b11ba"
HISTORICAL_INCIDENT_ID = "dedbd95d-8029-4116-ae6e-6bc220fdb347"
LIVE_SESSION_ID = "39062b0e-dc01-4a16-9fd3-5a03d6dd4bd7"


with SessionLocal() as db:
    historical_workflow = db.get(AgenticWorkflow, HISTORICAL_WORKFLOW_ID)
    historical_incident = db.get(Incident, HISTORICAL_INCIDENT_ID)
    historical_run = db.get(SimulationRun, historical_incident.simulation_id)
    historical_campaign = db.get(Campaign, historical_incident.campaign_id)
    historical_stage3 = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == historical_run.id,
        SimulationStage.stage_number == 3,
    ))

    live_session = db.get(LiveSimulationSession, LIVE_SESSION_ID)
    live_workflow = db.get(AgenticWorkflow, live_session.workflow_id)
    live_campaign = db.get(Campaign, live_session.campaign_id)
    live_stage3 = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == live_session.simulation_id,
        SimulationStage.stage_number == 3,
    ))
    live_approval = db.scalar(select(HumanApprovalRequest).where(
        HumanApprovalRequest.workflow_id == live_workflow.id,
    ))
    evidence_count = db.scalar(select(func.count(IncidentEvidence.id)).where(
        IncidentEvidence.incident_id == live_session.incident_id,
    ))
    agent_history = list(db.scalars(select(WorkflowHistory).where(
        WorkflowHistory.workflow_id == live_workflow.id,
    ).order_by(WorkflowHistory.sequence)))
    audit_actions = list(db.scalars(select(AuditLog.action).where(
        AuditLog.simulation_id == live_session.simulation_id,
    ).order_by(AuditLog.timestamp)))

    historical = {
        "workflow_status": historical_workflow.workflow_status,
        "approval_status": historical_workflow.approval_status,
        "campaign_status": historical_campaign.status,
        "simulation_status": historical_run.status,
        "current_stage": historical_run.current_stage,
        "canary_3_status": historical_stage3.status,
        "canary_3_task_id": historical_stage3.task_id,
        "anomaly_score": historical_incident.anomaly_score,
        "global_confidence": historical_workflow.global_confidence,
        "actions_executed": sum(bool(item.get("executed")) for item in historical_workflow.recommended_actions),
    }
    live = {
        "session_status": live_session.status,
        "source": live_session.source,
        "environment": live_session.environment,
        "campaign_status": live_campaign.status,
        "workflow_status": live_workflow.workflow_status,
        "approval_status": live_approval.status,
        "human_decision_user": live_approval.decided_by,
        "canary_3_exists": live_stage3 is not None,
        "actions_executed": sum(bool(item.get("executed")) for item in live_workflow.recommended_actions),
        "evidence_count": evidence_count,
        "history": [row.agent for row in agent_history],
        "audit_actions": audit_actions,
    }

assert historical == {
    "workflow_status": "WAITING_FOR_HUMAN_APPROVAL",
    "approval_status": "PENDING",
    "campaign_status": "draft",
    "simulation_status": "awaiting_evaluation",
    "current_stage": 2,
    "canary_3_status": "pending",
    "canary_3_task_id": None,
    "anomaly_score": None,
    "global_confidence": 0.620644,
    "actions_executed": 0,
}
assert live["session_status"] == "WAITING_FOR_HUMAN_APPROVAL"
assert live["approval_status"] == "PENDING"
assert live["human_decision_user"] is None
assert live["canary_3_exists"] is False
assert live["actions_executed"] == 0
assert live["history"] == ["MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION"]

print(json.dumps({"historical_invariants": historical, "live_invariants": live}, indent=2, ensure_ascii=False))
