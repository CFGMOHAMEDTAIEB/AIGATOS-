"""Read-only projections used by the AIGATOS operations interface.

The router intentionally exposes no campaign transition, approval, OTA action, or
LLM generation operation. Every value is projected from PostgreSQL or a live
dependency health check.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import get_db
from app.models import (
    AgenticWorkflow,
    AuditLog,
    Campaign,
    ECU,
    Incident,
    IncidentEvidence,
    IncidentExplanation,
    IncidentReport,
    LiveSimulationSession,
    OTAEvent,
    SimulationRun,
    SimulationStage,
    SimulationVehicle,
    SoftwarePackage,
    Vehicle,
    WorkflowHistory,
)


router = APIRouter(prefix="/api/v1/ui", tags=["frontend-read-model"])


def _latest_run(db: Session, campaign_id: str) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .where(SimulationRun.campaign_id == campaign_id)
        .order_by(SimulationRun.created_at.desc())
    )


def _stage_rows(db: Session, run_id: str) -> list[dict[str, Any]]:
    stages = db.scalars(
        select(SimulationStage)
        .where(SimulationStage.simulation_id == run_id)
        .order_by(SimulationStage.stage_number)
    )
    return [
        {
            "id": stage.id,
            "stage_number": stage.stage_number,
            "vehicle_count": stage.vehicle_count,
            "status": stage.status,
            "success_count": stage.success_count,
            "failure_count": stage.failure_count,
            "rollback_count": stage.rollback_count,
            "approved": stage.approved,
            "evaluated_by": stage.evaluated_by,
            "evaluated_at": stage.evaluated_at,
        }
        for stage in stages
    ]


def _campaign_row(db: Session, campaign: Campaign) -> dict[str, Any]:
    package = db.get(SoftwarePackage, campaign.software_package_id)
    run = _latest_run(db, campaign.id)
    live = db.scalar(select(LiveSimulationSession).where(LiveSimulationSession.campaign_id == campaign.id))
    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "canary_percentage": campaign.canary_percentage,
        "created_at": campaign.created_at,
        "source": "LIVE_SIMULATION" if live else "HISTORICAL_VALIDATED",
        "session_id": live.id if live else None,
        "software_package": None
        if package is None
        else {
            "id": package.id,
            "name": package.name,
            "version": package.version,
            "target_hardware": package.target_hardware,
        },
        "simulation": None
        if run is None
        else {
            "id": run.id,
            "status": run.status,
            "current_stage": run.current_stage,
            "failure_threshold": run.failure_threshold,
            "stages": _stage_rows(db, run.id),
        },
    }


def _context_row(db: Session, run: SimulationRun) -> dict[str, Any]:
    campaign = db.get(Campaign, run.campaign_id)
    package = db.get(SoftwarePackage, campaign.software_package_id) if campaign else None
    live = db.scalar(select(LiveSimulationSession).where(LiveSimulationSession.simulation_id == run.id))
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == run.id,
        SimulationStage.stage_number == run.current_stage,
    ))
    incident = db.scalar(select(Incident).where(
        Incident.simulation_id == run.id,
        Incident.stage_number == run.current_stage,
    ).order_by(Incident.created_at.desc()))
    workflow = db.scalar(select(AgenticWorkflow).where(
        AgenticWorkflow.incident_id == incident.id,
    )) if incident else None
    evidence_count = db.scalar(select(func.count()).select_from(IncidentEvidence).where(
        IncidentEvidence.incident_id == incident.id,
    )) if incident else 0
    return {
        "context_id": run.id,
        "source": "LIVE_SIMULATION" if live else "HISTORICAL_VALIDATED",
        "environment": "SIMULATED",
        "session_id": live.id if live else None,
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "campaign_status": campaign.status,
        "simulation_id": run.id,
        "simulation_status": live.status if live else run.status,
        "incident_id": incident.id if incident else None,
        "workflow_id": workflow.id if workflow else None,
        "workflow_status": workflow.workflow_status if workflow else None,
        "approval_status": workflow.approval_status if workflow else None,
        "software_name": package.name if package else None,
        "software_version": package.version if package else None,
        "stage_number": stage.stage_number if stage else run.current_stage,
        "vehicle_count": stage.vehicle_count if stage else 0,
        "progress_count": (stage.success_count + stage.failure_count) if stage else 0,
        "success_count": stage.success_count if stage else 0,
        "failure_count": stage.failure_count if stage else 0,
        "rollback_count": stage.rollback_count if stage else 0,
        "failure_rate": (stage.failure_count / stage.vehicle_count) if stage and stage.vehicle_count else 0.0,
        "evidence_count": evidence_count or 0,
        "global_confidence": workflow.global_confidence if workflow else None,
        "actions_executed": sum(bool(item.get("executed")) for item in (workflow.recommended_actions if workflow else [])),
        "created_by": live.created_by if live else "system",
        "created_at": live.created_at if live else run.created_at,
        "updated_at": live.updated_at if live else run.updated_at,
    }


def _service_health() -> dict[str, str]:
    redis_status = "indisponible"
    worker_status = "indisponible"
    try:
        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=0, timeout=0.5)
        redis_status = "opérationnel"
    except Exception:
        pass
    try:
        replies = celery_app.control.inspect(timeout=0.5).ping() or {}
        if replies:
            worker_status = "opérationnel"
    except Exception:
        pass
    return {"redis": redis_status, "celery_worker": worker_status}


@router.get("/contexts")
def contexts(
    scope: str = Query(default="all", pattern="^(all|historical|live)$"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = [_context_row(db, run) for run in db.scalars(select(SimulationRun).order_by(SimulationRun.created_at.desc()))]
    if scope == "historical":
        rows = [row for row in rows if row["source"] == "HISTORICAL_VALIDATED"]
    elif scope == "live":
        rows = [row for row in rows if row["source"] == "LIVE_SIMULATION"]
    return rows


@router.get("/dashboard")
def dashboard(
    simulation_id: str | None = Query(default=None),
    scope: str = Query(default="all", pattern="^(all|historical|live)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    available = contexts(scope=scope, db=db)
    if simulation_id:
        selected = next((row for row in available if row["simulation_id"] == simulation_id), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Simulation context not found")
        scoped = [selected]
    else:
        scoped = available
    total = sum(row["vehicle_count"] for row in scoped)
    successes = sum(row["success_count"] for row in scoped)
    failures = sum(row["failure_count"] for row in scoped)
    rollbacks = sum(row["rollback_count"] for row in scoped)
    processed = successes + failures
    dependency_health = _service_health()
    return {
        "scope": "active" if simulation_id else scope,
        "active_context": scoped[0] if len(scoped) == 1 else None,
        "campaign_count": len({row["campaign_id"] for row in scoped}),
        "tracked_vehicle_count": total,
        "simulation_participant_count": total,
        "progress_count": processed,
        "success_count": successes,
        "failure_count": failures,
        "rollback_count": rollbacks,
        "success_rate": successes / processed if processed else 0.0,
        "failure_rate": failures / processed if processed else 0.0,
        "open_incident_count": sum(bool(row["incident_id"]) for row in scoped),
        "waiting_workflow_count": sum(row["workflow_status"] == "WAITING_FOR_HUMAN_APPROVAL" for row in scoped),
        "services": {
            "api": "opérationnel",
            "postgresql": "opérationnel",
            **dependency_health,
        },
    }


@router.get("/campaigns")
def campaigns(scope: str = Query(default="all", pattern="^(all|historical|live)$"), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = [_campaign_row(db, campaign) for campaign in db.scalars(select(Campaign).order_by(Campaign.created_at.desc()))]
    if scope == "historical":
        rows = [row for row in rows if row["source"] == "HISTORICAL_VALIDATED"]
    elif scope == "live":
        rows = [row for row in rows if row["source"] == "LIVE_SIMULATION"]
    return rows


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_row(db, campaign)


def _vehicle_row(db: Session, vehicle: Vehicle) -> dict[str, Any]:
    ecu = db.scalar(select(ECU).where(ECU.vehicle_id == vehicle.id).order_by(ECU.created_at))
    participant = db.scalar(
        select(SimulationVehicle)
        .where(SimulationVehicle.vehicle_id == vehicle.id)
        .order_by(SimulationVehicle.processed_at.desc().nullslast())
    )
    run = db.get(SimulationRun, participant.simulation_id) if participant else None
    campaign = db.get(Campaign, run.campaign_id) if run else None
    package = db.get(SoftwarePackage, campaign.software_package_id) if campaign else None
    live = db.scalar(select(LiveSimulationSession).where(LiveSimulationSession.simulation_id == run.id)) if run else None
    return {
        "id": vehicle.id,
        "vin": vehicle.vin,
        "model": vehicle.model,
        "region": None,
        "hardware_revision": ecu.hardware_version if ecu else vehicle.hardware_version,
        "ecu": None if ecu is None else {"id": ecu.id, "name": ecu.name},
        "current_version": ecu.software_version if ecu else None,
        "target_version": package.version if package else None,
        "ota_status": (
            "SUCCESS" if participant and participant.outcome == "success"
            else "FAILURE" if participant and participant.outcome is not None
            else "NOT_STARTED"
        ),
        "rolled_back": participant.rolled_back if participant else False,
        "simulation_id": run.id if run else None,
        "campaign_id": campaign.id if campaign else None,
        "source": "LIVE_SIMULATION" if live else "HISTORICAL_VALIDATED",
        "session_id": live.id if live else None,
    }


@router.get("/vehicles")
def vehicles(
    q: str | None = Query(default=None, max_length=100),
    hardware_revision: str | None = Query(default=None, max_length=100),
    ota_status: str | None = Query(default=None, max_length=40),
    scope: str = Query(default="all", pattern="^(all|historical|live)$"),
    simulation_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = list(db.scalars(select(Vehicle).order_by(Vehicle.vin)))
    projected = [_vehicle_row(db, vehicle) for vehicle in rows]
    if q:
        needle = q.casefold()
        projected = [
            row for row in projected
            if needle in row["vin"].casefold() or needle in row["model"].casefold()
        ]
    if hardware_revision:
        projected = [row for row in projected if row["hardware_revision"] == hardware_revision]
    if ota_status:
        projected = [row for row in projected if row["ota_status"] == ota_status]
    if scope == "historical":
        projected = [row for row in projected if row["source"] == "HISTORICAL_VALIDATED"]
    elif scope == "live":
        projected = [row for row in projected if row["source"] == "LIVE_SIMULATION"]
    if simulation_id:
        projected = [row for row in projected if row["simulation_id"] == simulation_id]
    return {"total": len(projected), "items": projected[offset : offset + limit]}


@router.get("/audit")
def audit_history(
    simulation_id: str = Query(),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation context not found")
    context = _context_row(db, run)
    entries = [{
        "id": row.id,
        "timestamp": row.timestamp,
        "category": "SIMULATION",
        "actor": row.actor,
        "action": row.action,
        "status": row.decision,
        "summary": row.reason,
        "details": row.details,
    } for row in db.scalars(select(AuditLog).where(
        AuditLog.simulation_id == simulation_id,
    ).order_by(AuditLog.timestamp))]
    if context["workflow_id"]:
        entries.extend({
            "id": row.id,
            "timestamp": row.created_at,
            "category": "AGENT",
            "actor": row.agent,
            "action": row.event_type,
            "status": "ERROR" if row.error_type else "COMPLETED",
            "summary": f"{row.agent}: {row.output_summary}",
            "details": {
                "sequence": row.sequence,
                "duration_ms": row.duration_ms,
                "input": row.input_summary,
                "output": row.output_summary,
                "error": row.error_message,
            },
        } for row in db.scalars(select(WorkflowHistory).where(
            WorkflowHistory.workflow_id == context["workflow_id"],
        ).order_by(WorkflowHistory.sequence)))
    entries.sort(key=lambda item: item["timestamp"])
    return {"context": context, "entries": entries}


@router.get("/vehicles/{vehicle_id}")
def vehicle_detail(vehicle_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    row = _vehicle_row(db, vehicle)
    events = list(
        db.scalars(
            select(OTAEvent).where(OTAEvent.vehicle_id == vehicle_id).order_by(OTAEvent.timestamp, OTAEvent.sequence)
        )
    )
    row["timeline"] = [
        {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "installation_step": event.installation_step,
            "error_code": event.error_code,
            "battery_level": event.battery_level,
            "network_quality": event.network_quality,
            "free_storage_mb": event.free_storage_mb,
        }
        for event in events
    ]
    return row


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    stage = db.scalar(
        select(SimulationStage).where(
            SimulationStage.simulation_id == incident.simulation_id,
            SimulationStage.stage_number == incident.stage_number,
        )
    )
    participants = list(
        db.scalars(
            select(SimulationVehicle).where(
                SimulationVehicle.simulation_id == incident.simulation_id,
                SimulationVehicle.stage_number == incident.stage_number,
            )
        )
    )
    hardware: dict[str, dict[str, int]] = {}
    for participant in participants:
        ecu = db.get(ECU, participant.ecu_id)
        revision = ecu.hardware_version if ecu else "INCONNU"
        bucket = hardware.setdefault(revision, {"total": 0, "success": 0, "failure": 0})
        bucket["total"] += 1
        key = "success" if participant.outcome == "success" else "failure"
        bucket[key] += 1
    failure_events = list(
        db.scalars(
            select(OTAEvent).where(
                OTAEvent.simulation_id == incident.simulation_id,
                OTAEvent.stage_number == incident.stage_number,
                OTAEvent.event_type == "FAILURE",
            )
        )
    )
    workflow = db.scalar(
        select(AgenticWorkflow).where(AgenticWorkflow.incident_id == incident.id)
    )
    normalized_errors = (
        [
            {
                "error_code": item.get("error_code", "UNKNOWN"),
                "installation_step": item.get("installation_step", "UNKNOWN"),
                "count": item.get("count", 0),
            }
            for item in workflow.normalized_errors
        ]
        if workflow is not None
        else [
            {"error_code": code, "installation_step": step, "count": count}
            for (code, step), count in sorted(
                Counter((event.error_code or "UNKNOWN", event.installation_step) for event in failure_events).items()
            )
        ]
    )
    return {
        "id": incident.id,
        "campaign_id": incident.campaign_id,
        "simulation_id": incident.simulation_id,
        "stage_number": incident.stage_number,
        "status": incident.status,
        "severity": incident.severity,
        "title": incident.title,
        "failure_rate": incident.failure_rate,
        "threshold": incident.threshold,
        "anomaly_score": incident.anomaly_score,
        "created_at": incident.created_at,
        "vehicle_count": stage.vehicle_count if stage else len(participants),
        "success_count": stage.success_count if stage else 0,
        "failure_count": stage.failure_count if stage else 0,
        "rollback_count": stage.rollback_count if stage else 0,
        "linked_event_count": db.scalar(
            select(func.count()).select_from(IncidentEvidence).where(IncidentEvidence.incident_id == incident.id)
        ) or 0,
        "failure_event_count": len(failure_events),
        "normalized_errors": normalized_errors,
        "hardware_distribution": [
            {"hardware_revision": revision, **counts}
            for revision, counts in sorted(hardware.items())
        ],
    }


@router.get("/incidents/{incident_id}/reports")
def incident_reports(incident_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if db.get(Incident, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    rows = db.scalars(
        select(IncidentReport)
        .where(IncidentReport.incident_id == incident_id)
        .order_by(IncidentReport.version.desc())
    )
    return [
        {
            "report_id": report.id,
            "incident_id": report.incident_id,
            "workflow_id": report.workflow_id,
            "explanation_id": report.explanation_id,
            "version": report.version,
            "template_version": report.template_version,
            "pdf_sha256": report.pdf_sha256,
            "generated_at": report.generated_at,
            "download_url": f"/reports/{report.id}/pdf",
            "source": (
                explanation.source
                if (explanation := db.get(IncidentExplanation, report.explanation_id)) is not None
                else None
            ),
        }
        for report in rows
    ]


@router.get("/incidents/{incident_id}/explanation")
def incident_explanation(incident_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    explanation = db.scalar(
        select(IncidentExplanation)
        .where(IncidentExplanation.incident_id == incident_id)
        .order_by(IncidentExplanation.created_at.desc())
    )
    if explanation is None:
        raise HTTPException(status_code=404, detail="Explanation not found")
    return {
        "id": explanation.id,
        "workflow_id": explanation.workflow_id,
        "incident_id": explanation.incident_id,
        "provider": explanation.provider,
        "model_name": explanation.model_name,
        "prompt_version": explanation.prompt_version,
        "source": explanation.source,
        "status": explanation.status,
        "output": explanation.output,
        "duration_ms": explanation.duration_ms,
        "created_at": explanation.created_at,
    }
