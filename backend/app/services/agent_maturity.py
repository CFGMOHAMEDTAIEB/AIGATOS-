from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgenticWorkflow, IncidentEvidence, WorkflowHistory
from app.services.agentic_workflow import AGENTS


AGENT_DETAILS = {
    "MONITORING": ("Monitoring", "Détecte les dépassements de seuil et rassemble les preuves.", ["test_monitoring_agent.py", "test_services_integration.py"]),
    "LOG_ANALYSIS": ("Log Analysis", "Normalise les erreurs et reconstruit les chronologies véhicule.", ["test_agentic_workflow.py::test_full_agent_chain"]),
    "CORRELATION": ("Correlation", "Compare les cohortes et quantifie les associations observées.", ["test_agentic_workflow.py::test_full_agent_chain"]),
    "RCA": ("RCA", "Classe les hypothèses explicables à partir des preuves valides.", ["test_agentic_workflow.py::test_hypothesis_without_evidence_rejected"]),
    "DECISION": ("Decision", "Produit des actions proposées soumises à validation humaine.", ["test_agentic_workflow.py::test_no_action_before_approval"]),
}


def calculate_agent_maturity(db: Session) -> dict:
    workflows = list(db.scalars(select(AgenticWorkflow).order_by(AgenticWorkflow.created_at.desc())))
    rows = list(db.scalars(select(WorkflowHistory).where(WorkflowHistory.agent.in_(AGENTS)).order_by(WorkflowHistory.created_at.desc())))
    output = []
    for agent in AGENTS:
        name, role, tests = AGENT_DETAILS[agent]
        agent_rows = [row for row in rows if row.agent == agent]
        completed = [row for row in agent_rows if row.event_type == "AGENT_COMPLETED"]
        errors = [row for row in agent_rows if row.event_type == "AGENT_ERROR"]
        safe_workflow = None
        for workflow in workflows:
            if not any(row.workflow_id == workflow.id for row in completed):
                continue
            evidence_count = db.scalar(select(func.count()).select_from(IncidentEvidence).where(
                IncidentEvidence.incident_id == workflow.incident_id,
            )) or 0
            if (
                evidence_count > 0
                and workflow.workflow_status in {"WAITING_FOR_HUMAN_APPROVAL", "HUMAN_APPROVED", "HUMAN_REJECTED"}
                and all(not item.get("executed", False) for item in workflow.recommended_actions)
            ):
                safe_workflow = workflow
                break
        criteria = {
            "M1": {"satisfied": True, "label": "Implémentation présente"},
            "M2": {"satisfied": bool(tests), "label": "Tests unitaires associés"},
            "M3": {"satisfied": bool(completed), "label": "Intégration persistante et idempotente"},
            "M4": {"satisfied": safe_workflow is not None, "label": "Workflow complet avec preuves et arrêt humain"},
            "M5": {"satisfied": False, "label": "Validation automobile, cybersécurité et conformité"},
        }
        level = "M4" if criteria["M4"]["satisfied"] else "M3" if criteria["M3"]["satisfied"] else "M2"
        output.append({
            "agent": agent, "name": name, "role": role, "current_level": level,
            "execution_status": "COMPLETED" if completed else "IDLE",
            "criteria": criteria,
            "technical_evidence": ([
                f"workflow_id={safe_workflow.id}",
                f"incident_id={safe_workflow.incident_id}",
                f"evidence_count={len(safe_workflow.evidence_ids)}",
                "ota_actions_executed=0",
            ] if safe_workflow else ["Implémentation et tests présents"]),
            "associated_tests": tests,
            "last_execution": agent_rows[0].created_at if agent_rows else None,
            "duration_ms": agent_rows[0].duration_ms if agent_rows else None,
            "input_summary": agent_rows[0].input_summary if agent_rows else {},
            "output_summary": agent_rows[0].output_summary if agent_rows else {},
            "recent_errors": [row.error_message for row in errors[:3] if row.error_message],
            "limitations": [
                "Données et véhicules simulés uniquement",
                "Aucune certification officielle",
                "Aucune validation en production automobile",
            ],
            "next_level": "M5" if level == "M4" else f"M{int(level[1]) + 1}",
            "next_level_conditions": (
                ["Validation sur véhicule réel", "Validation cybersécurité", "Validation opérationnelle", "Processus qualité et conformité"]
                if level == "M4" else [criteria[f"M{int(level[1]) + 1}"]["label"]]
            ),
        })
    return {
        "scale": [
            {"level": "M0", "label": "Non défini"}, {"level": "M1", "label": "Prototype local"},
            {"level": "M2", "label": "Intégration initiale"}, {"level": "M3", "label": "Workflow supervisé"},
            {"level": "M4", "label": "Fonctionnement validé en environnement simulé"},
            {"level": "M5", "label": "Production automobile validée"},
        ],
        "agents": output,
        "certification_notice": "Échelle interne de maturité, non constitutive d’une certification officielle.",
        "m5_available": False,
    }
