from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm_config import LLMConfigurationError, load_llm_settings
from app.models import AgenticWorkflow, IncidentExplanation, LLMCallAudit
from app.services.diagnostic_explanation import generate_explanation


router = APIRouter(tags=["diagnostic-explanations"])


def _response(explanation: IncidentExplanation, audit: LLMCallAudit | None, cache_hit: bool) -> dict:
    return {
        "explanation_id": explanation.id,
        "workflow_id": explanation.workflow_id,
        "incident_id": explanation.incident_id,
        "source": explanation.source,
        "status": explanation.status,
        "cache_hit": cache_hit,
        "output": explanation.output,
        "audit": None if audit is None else {
            "audit_id": audit.id,
            "provider": audit.provider,
            "model": audit.model_name,
            "prompt_version": audit.prompt_version,
            "duration_ms": audit.duration_ms,
            "status": audit.status,
            "attempt_count": audit.attempt_count,
            "prompt_tokens": audit.prompt_tokens,
            "completion_tokens": audit.completion_tokens,
            "total_tokens": audit.total_tokens,
            "created_at": audit.created_at,
        },
        "created_at": explanation.created_at,
    }


@router.post("/incidents/{incident_id}/explanations")
def create_explanation(incident_id: str, db: Session = Depends(get_db)) -> dict:
    workflow = db.scalar(select(AgenticWorkflow).where(AgenticWorkflow.incident_id == incident_id))
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        settings = load_llm_settings()
        explanation, audit, cache_hit = generate_explanation(db, workflow.id, settings)
    except (ValueError, LLMConfigurationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _response(explanation, audit, cache_hit)


@router.get("/incidents/{incident_id}/explanations/latest")
def latest_explanation(incident_id: str, db: Session = Depends(get_db)) -> dict:
    explanation = db.scalar(select(IncidentExplanation).where(
        IncidentExplanation.incident_id == incident_id,
    ).order_by(IncidentExplanation.created_at.desc()))
    if explanation is None:
        raise HTTPException(status_code=404, detail="Explanation not found")
    audit = db.scalar(select(LLMCallAudit).where(
        LLMCallAudit.explanation_id == explanation.id,
    ).order_by(LLMCallAudit.created_at.desc()))
    return _response(explanation, audit, audit.status == "CACHE_HIT" if audit else False)


@router.get("/explanations/{explanation_id}/audit")
def explanation_audit(explanation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(IncidentExplanation, explanation_id) is None:
        raise HTTPException(status_code=404, detail="Explanation not found")
    audits = list(db.scalars(select(LLMCallAudit).where(
        LLMCallAudit.explanation_id == explanation_id,
    ).order_by(LLMCallAudit.created_at)))
    return [_response(db.get(IncidentExplanation, explanation_id), audit, audit.status == "CACHE_HIT")["audit"] for audit in audits]
