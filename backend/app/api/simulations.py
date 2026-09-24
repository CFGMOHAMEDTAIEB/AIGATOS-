from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, Campaign, Incident, OTAEvent, SimulationRun, SimulationStage, SimulationVehicle
from app.schemas.simulation import SimulationCreate, StageEvaluation
from app.services.ota_simulator import STAGE_SIZES
from app.tasks import simulate_stage

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


def get_run(db: Session, simulation_id: str) -> SimulationRun:
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return run


def summary(db: Session, run: SimulationRun) -> dict:
    stages = list(db.scalars(select(SimulationStage).where(
        SimulationStage.simulation_id == run.id,
    ).order_by(SimulationStage.stage_number)))
    incident = db.scalar(select(Incident).where(Incident.simulation_id == run.id).order_by(Incident.stage_number.desc()))
    audits = list(db.scalars(select(AuditLog).where(AuditLog.simulation_id == run.id).order_by(AuditLog.timestamp)))
    return {
        "id": run.id,
        "campaign_id": run.campaign_id,
        "seed": run.seed,
        "hw_b_failure_probability": run.hw_b_failure_probability,
        "failure_threshold": run.failure_threshold,
        "status": run.status,
        "current_stage": run.current_stage,
        "created_at": run.created_at,
        "incident": None if incident is None else {
            "id": incident.id, "stage_number": incident.stage_number, "status": incident.status,
            "severity": incident.severity, "failure_rate": incident.failure_rate,
            "threshold": incident.threshold, "title": incident.title, "created_at": incident.created_at,
            "metadata": incident.details,
        },
        "audit_log": [{
            "id": item.id, "stage_number": item.stage_number, "action": item.action,
            "actor": item.actor, "decision": item.decision, "reason": item.reason,
            "timestamp": item.timestamp, "metadata": item.details,
        } for item in audits],
        "stages": [{
            "stage_number": stage.stage_number,
            "vehicle_count": stage.vehicle_count,
            "status": stage.status,
            "success_count": stage.success_count,
            "failure_count": stage.failure_count,
            "rollback_count": stage.rollback_count,
            "approved": stage.approved,
            "evaluation_note": stage.evaluation_note,
            "evaluated_by": stage.evaluated_by,
            "evaluated_at": stage.evaluated_at,
            "task_id": stage.task_id,
        } for stage in stages],
    }


def enqueue(db: Session, run: SimulationRun, stage: SimulationStage) -> None:
    try:
        task = simulate_stage.delay(run.id, stage.stage_number)
        stage.task_id = task.id
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(SimulationRun, run.id)
        stage = db.get(SimulationStage, stage.id)
        run.status = "enqueue_failed"
        stage.status = "enqueue_failed"
        db.commit()
        raise HTTPException(status_code=503, detail="Simulation queue unavailable") from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def launch(payload: SimulationCreate, db: Session = Depends(get_db)) -> dict:
    campaign = db.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft campaigns can be simulated")
    run = SimulationRun(
        campaign_id=campaign.id, seed=payload.seed,
        hw_b_failure_probability=payload.hw_b_failure_probability,
        failure_threshold=payload.failure_threshold,
        status="queued", current_stage=1,
    )
    db.add(run)
    db.flush()
    stages = [
        SimulationStage(
            simulation_id=run.id, stage_number=n,
            vehicle_count=size, status="queued" if n == 1 else "pending",
        )
        for n, size in enumerate(STAGE_SIZES, 1)
    ]
    db.add_all(stages)
    db.commit()
    enqueue(db, run, stages[0])
    return summary(db, run)


@router.get("/{simulation_id}")
def retrieve(simulation_id: str, db: Session = Depends(get_db)) -> dict:
    return summary(db, get_run(db, simulation_id))


@router.post("/{simulation_id}/stages/{stage_number}/evaluate")
def evaluate(
    simulation_id: str, stage_number: int, payload: StageEvaluation,
    db: Session = Depends(get_db),
) -> dict:
    run = get_run(db, simulation_id)
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == stage_number,
    ))
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    if stage_number != run.current_stage or stage.status != "awaiting_evaluation":
        raise HTTPException(status_code=409, detail="Stage is not ready for evaluation")
    stage.approved = payload.approved
    stage.evaluation_note = payload.note
    stage.evaluated_by = payload.reviewer
    stage.evaluated_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        simulation_id=run.id, stage_number=stage_number, action="CANARY_STAGE_EVALUATION",
        actor=payload.reviewer, decision="APPROVE" if payload.approved else "REJECT",
        reason=payload.note, details={
            "simulation_only": True, "success_count": stage.success_count,
            "failure_count": stage.failure_count, "rollback_count": stage.rollback_count,
        },
    ))
    stage.status = "approved" if payload.approved else "rejected"
    if not payload.approved:
        run.status = "rejected"
    elif stage_number == 3:
        run.status = "completed"
    else:
        run.status = "awaiting_advance"
    db.commit()
    return summary(db, run)


@router.post("/{simulation_id}/advance", status_code=status.HTTP_202_ACCEPTED)
def advance(simulation_id: str, db: Session = Depends(get_db)) -> dict:
    run = get_run(db, simulation_id)
    if run.status != "awaiting_advance" or run.current_stage >= 3:
        raise HTTPException(status_code=409, detail="Current stage has not been approved")
    previous = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == run.current_stage,
    ))
    if previous is None or previous.approved is not True:
        raise HTTPException(status_code=409, detail="Evaluation approval required")
    next_stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == run.current_stage + 1,
    ))
    if next_stage is None or next_stage.status != "pending":
        raise HTTPException(status_code=409, detail="Next stage unavailable")
    run.current_stage += 1
    run.status = "queued"
    next_stage.status = "queued"
    db.commit()
    enqueue(db, run, next_stage)
    return summary(db, run)


@router.get("/{simulation_id}/vehicles/{vehicle_id}/timeline")
def vehicle_timeline(simulation_id: str, vehicle_id: str, db: Session = Depends(get_db)) -> list[dict]:
    get_run(db, simulation_id)
    participant = db.scalar(select(SimulationVehicle).where(
        SimulationVehicle.simulation_id == simulation_id,
        SimulationVehicle.vehicle_id == vehicle_id,
    ))
    if participant is None:
        raise HTTPException(status_code=404, detail="Vehicle not in simulation")
    events = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == simulation_id,
        OTAEvent.vehicle_id == vehicle_id,
    ).order_by(OTAEvent.sequence)))
    return [{
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "campaign_id": event.campaign_id,
        "vehicle_id": event.vehicle_id,
        "ecu_id": event.ecu_id,
        "event_type": event.event_type,
        "installation_step": event.installation_step,
        "error_code": event.error_code,
        "software_version": event.software_version,
        "hardware_revision": event.hardware_revision,
        "battery_level": event.battery_level,
        "network_quality": event.network_quality,
        "free_storage_mb": event.free_storage_mb,
        "attempt_number": event.attempt_number,
        "metadata": event.details,
    } for event in events]
