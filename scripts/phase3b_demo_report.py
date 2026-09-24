"""Read-only PostgreSQL proof report for a completed Phase 3B workflow."""

import argparse
import json

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    AgenticWorkflow, Campaign, HumanApprovalRequest, Incident, IncidentEvidence,
    SimulationRun, SimulationStage, WorkflowHistory,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("incident_id")
    args = parser.parse_args()
    with SessionLocal() as db:
        incident = db.get(Incident, args.incident_id)
        workflow = db.scalar(select(AgenticWorkflow).where(AgenticWorkflow.incident_id == args.incident_id))
        if incident is None or workflow is None:
            raise SystemExit("Incident or workflow not found")
        run = db.get(SimulationRun, incident.simulation_id)
        campaign = db.get(Campaign, incident.campaign_id)
        stages = list(db.scalars(select(SimulationStage).where(
            SimulationStage.simulation_id == incident.simulation_id,
        ).order_by(SimulationStage.stage_number)))
        history = list(db.scalars(select(WorkflowHistory).where(
            WorkflowHistory.workflow_id == workflow.id,
        ).order_by(WorkflowHistory.sequence)))
        approval = db.scalar(select(HumanApprovalRequest).where(
            HumanApprovalRequest.workflow_id == workflow.id,
        ))
        evidence_count = db.scalar(select(func.count()).select_from(IncidentEvidence).where(
            IncidentEvidence.incident_id == incident.id,
        ))
        evidence_set = set(db.scalars(select(IncidentEvidence.id).where(
            IncidentEvidence.incident_id == incident.id,
        )))
        cited = {
            evidence_id
            for hypothesis in workflow.hypotheses
            for evidence_id in hypothesis.get("evidence_ids", [])
        }
        selected_correlations = [
            value for value in workflow.correlations
            if value.get("factor") in {
                "hardware_revision", "software_version", "package", "battery_level",
                "network_quality", "free_storage_mb",
            }
        ]
        report = {
            "workflow": {
                "workflow_id": workflow.id,
                "incident_id": workflow.incident_id,
                "status": workflow.workflow_status,
                "current_agent": workflow.current_agent,
                "approval_status": workflow.approval_status,
                "retry_count": workflow.retry_count,
                "last_error": workflow.last_error,
                "global_confidence": workflow.global_confidence,
            },
            "history": [{
                "sequence": row.sequence,
                "agent": row.agent,
                "event_type": row.event_type,
                "duration_ms": row.duration_ms,
                "output_summary": row.output_summary,
                "error_type": row.error_type,
            } for row in history],
            "normalized_errors": workflow.normalized_errors,
            "correlations": selected_correlations,
            "hypotheses": workflow.hypotheses,
            "confidence_components": workflow.confidence_components,
            "recommended_actions": workflow.recommended_actions,
            "postgresql_evidence": {
                "linked_count": evidence_count,
                "workflow_evidence_count": len(workflow.evidence_ids),
                "hypothesis_citation_count": len(cited),
                "invalid_hypothesis_evidence_ids": sorted(cited - evidence_set),
                "sample_evidence_ids": sorted(evidence_set)[:10],
            },
            "safety_invariants": {
                "incident_anomaly_score": incident.anomaly_score,
                "campaign_status": campaign.status,
                "simulation_status": run.status,
                "simulation_current_stage": run.current_stage,
                "stages": [{
                    "stage_number": stage.stage_number,
                    "status": stage.status,
                    "task_id": stage.task_id,
                } for stage in stages],
                "approval_request_status": approval.status if approval else None,
                "approval_decided_at": approval.decided_at if approval else None,
                "executed_action_count": sum(
                    bool(action.get("executed")) for action in workflow.recommended_actions
                ),
            },
        }
        if workflow.workflow_status != "WAITING_FOR_HUMAN_APPROVAL":
            raise SystemExit("Workflow is not waiting for human approval")
        print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
