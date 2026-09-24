from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LiveSimulationSession
from app.operation_mode import capabilities, get_operation_mode
from app.schemas.live import LiveDecision, LiveSimulationCreate
from app.services.agent_maturity import calculate_agent_maturity
from app.services.agentic_workflow import record_human_decision
from app.services.live_simulation import (
    _audit, _summary, create_live_session, get_live_session, investigate_live_session,
    live_events, live_workflow, start_live_session,
)


router = APIRouter(tags=["live-simulation"])


def _require_live_mode() -> None:
    if get_operation_mode() != "live_simulation":
        raise HTTPException(status_code=403, detail="Live simulation mode is disabled")


def _key(value: str | None) -> str:
    if value is None or not 8 <= len(value) <= 100:
        raise HTTPException(status_code=422, detail="A valid Idempotency-Key header is required")
    return value


@router.get("/frontend/capabilities")
def frontend_capabilities() -> dict:
    return capabilities()


@router.post("/live-simulations", status_code=status.HTTP_201_CREATED)
def create(
    payload: LiveSimulationCreate, db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_live_mode()
    result, created = create_live_session(db, payload, _key(idempotency_key))
    return {**result, "created": created}


@router.post("/live-simulations/{session_id}/start")
def start(
    session_id: str, db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_live_mode()
    try:
        return start_live_session(db, session_id, _key(idempotency_key))
    except ValueError as error:
        raise HTTPException(status_code=404 if "Unknown" in str(error) else 409, detail=str(error)) from error


@router.get("/live-simulations/{session_id}")
def retrieve(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return _summary(db, get_live_session(db, session_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/live-simulations/{session_id}/events")
def events(session_id: str, db: Session = Depends(get_db)) -> list[dict]:
    try:
        return live_events(db, session_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/live-simulations/{session_id}/investigation")
def investigation(
    session_id: str, db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_live_mode()
    try:
        return investigate_live_session(db, session_id, _key(idempotency_key))
    except ValueError as error:
        raise HTTPException(status_code=404 if "Unknown" in str(error) else 409, detail=str(error)) from error


@router.get("/live-simulations/{session_id}/workflow")
def workflow(session_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return live_workflow(db, session_id)
    except ValueError as error:
        raise HTTPException(status_code=404 if "Unknown" in str(error) else 409, detail=str(error)) from error


@router.post("/live-simulations/{session_id}/decision")
def decision(
    session_id: str, payload: LiveDecision, db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    _require_live_mode()
    key = _key(idempotency_key)
    try:
        session = get_live_session(db, session_id)
        if session.decision_key == key:
            return {**_summary(db, session), "decision_recorded": True, "executed": False}
        if session.decision_key is not None:
            raise ValueError("A decision has already been recorded")
        if not session.workflow_id:
            raise ValueError("Investigation has not been started")
        workflow_row = record_human_decision(
            db, session.workflow_id, payload.approved, payload.user, payload.timestamp, payload.comment,
        )
        session = db.get(LiveSimulationSession, session_id)
        session.decision_key = key
        session.status = workflow_row.workflow_status
        _audit(db, session, "LIVE_HUMAN_DECISION", workflow_row.approval_status, payload.comment, key)
        db.commit()
        return {
            **_summary(db, session), "decision_recorded": True, "executed": False,
            "message": "Décision enregistrée, exécution désactivée dans l’environnement simulé",
        }
    except ValueError as error:
        raise HTTPException(status_code=404 if "Unknown" in str(error) else 409, detail=str(error)) from error


@router.get("/agent-maturity")
def maturity(db: Session = Depends(get_db)) -> dict:
    return calculate_agent_maturity(db)
