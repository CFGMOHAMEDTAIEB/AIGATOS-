from __future__ import annotations

import math
from datetime import datetime, timezone
from hashlib import sha256
from random import Random
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgenticWorkflow, AuditLog, Campaign, ECU, Incident, LiveSimulationSession,
    OTAEvent, SimulationRun, SimulationStage, SimulationVehicle, SoftwarePackage,
    Vehicle, WorkflowHistory,
)
from app.schemas.live import LiveSimulationCreate
from app.services.agentic_workflow import create_workflow, run_workflow, workflow_state
from app.services.incident_report import generate_automatic_report
from app.services.monitoring_agent import MonitoringThresholds, monitor_stage


SOURCE = "LIVE_SIMULATION"
ENVIRONMENT = "SIMULATED"
SUCCESS_PATH = [
    "IDLE", "ELIGIBILITY_CHECK", "DOWNLOADING", "VERIFYING_PACKAGE", "INSTALLING",
    "MEMORY_VALIDATION", "REBOOTING", "HEALTH_CHECK", "SUCCESS",
]
DEFAULT_FAILURES = {
    "battery_insufficient": ("ELIGIBILITY_CHECK", "BATTERY_INSUFFICIENT", False),
    "network_unstable": ("DOWNLOADING", "NETWORK_UNSTABLE", False),
    "storage_insufficient": ("ELIGIBILITY_CHECK", "STORAGE_INSUFFICIENT", False),
    "package_corrupted": ("VERIFYING_PACKAGE", "PACKAGE_CORRUPTED", False),
    "hardware_software_incompatible": ("MEMORY_VALIDATION", "MEMORY_LAYOUT_MISMATCH", True),
    "ecu_unresponsive": ("REBOOTING", "ECU_NOT_RESPONDING", True),
    "failure_with_rollback": ("INSTALLING", "INSTALLATION_FAILED", True),
}


def _trace(session: LiveSimulationSession) -> dict:
    return {
        "source": SOURCE, "environment": ENVIRONMENT, "session_id": session.id,
        "created_by": session.created_by, "created_at": session.created_at.isoformat(),
        "simulation_only": True, "real_ota_allowed": False,
    }


def _audit(db: Session, session: LiveSimulationSession, action: str, decision: str, reason: str, key: str) -> None:
    existing = db.scalar(select(AuditLog).where(
        AuditLog.simulation_id == session.simulation_id,
        AuditLog.action == action,
    ))
    if existing is not None:
        return
    db.add(AuditLog(
        simulation_id=session.simulation_id, stage_number=1, action=action,
        actor=session.created_by, decision=decision, reason=reason,
        details={**_trace(session), "idempotency_key": key},
    ))


def _summary(db: Session, session: LiveSimulationSession) -> dict:
    run = db.get(SimulationRun, session.simulation_id)
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == session.simulation_id,
        SimulationStage.stage_number == 1,
    ))
    # COUNT is kept database-portable for PostgreSQL and the SQLite test suite.
    events = list(db.scalars(select(OTAEvent).where(OTAEvent.simulation_id == session.simulation_id)))
    workflow = db.get(AgenticWorkflow, session.workflow_id) if session.workflow_id else None
    return {
        "id": session.id, "session_id": session.id, "source": session.source,
        "environment": session.environment, "created_by": session.created_by,
        "created_at": session.created_at, "updated_at": session.updated_at,
        "status": session.status, "campaign_id": session.campaign_id,
        "simulation_id": session.simulation_id, "incident_id": session.incident_id,
        "workflow_id": session.workflow_id, "configuration": session.configuration,
        "result": session.result, "current_stage": run.current_stage,
        "stage": {
            "stage_number": stage.stage_number, "vehicle_count": stage.vehicle_count,
            "status": stage.status, "success_count": stage.success_count,
            "failure_count": stage.failure_count, "rollback_count": stage.rollback_count,
            "progress_count": stage.success_count + stage.failure_count,
        },
        "event_count": len(events),
        "workflow": workflow_state(workflow) if workflow else None,
        "executed": False, "can_execute_real_ota": False,
    }


def get_live_session(db: Session, session_id: str) -> LiveSimulationSession:
    session = db.get(LiveSimulationSession, session_id)
    if session is None:
        raise ValueError("Unknown live simulation session")
    return session


def create_live_session(db: Session, payload: LiveSimulationCreate, idempotency_key: str) -> tuple[dict, bool]:
    existing = db.scalar(select(LiveSimulationSession).where(LiveSimulationSession.creation_key == idempotency_key))
    if existing is not None:
        return _summary(db, existing), False
    session_id = str(uuid4())
    package = db.scalar(select(SoftwarePackage).where(
        SoftwarePackage.name == payload.campaign.component,
        SoftwarePackage.version == payload.campaign.target_version,
    ))
    if package is None:
        package = SoftwarePackage(
            name=payload.campaign.component, version=payload.campaign.target_version,
            target_hardware="SIMULATED_MULTI_HW",
            checksum_sha256=sha256(f"{SOURCE}:{session_id}".encode()).hexdigest(),
        )
        db.add(package); db.flush()
    campaign = Campaign(
        name=f"{payload.campaign.name} · {session_id[:8]}",
        software_package_id=package.id, status="draft", canary_percentage=100,
    )
    db.add(campaign); db.flush()
    run = SimulationRun(
        campaign_id=campaign.id, seed=payload.seed, hw_b_failure_probability=0,
        failure_threshold=payload.campaign.failure_threshold,
        status="PREPARING", current_stage=1,
    )
    db.add(run); db.flush()
    db.add(SimulationStage(
        simulation_id=run.id, stage_number=1, vehicle_count=payload.fleet.vehicle_count,
        status="PREPARING",
    ))
    session = LiveSimulationSession(
        id=session_id, created_by=payload.created_by, campaign_id=campaign.id,
        simulation_id=run.id, configuration=payload.model_dump(mode="json"),
        result={}, creation_key=idempotency_key,
    )
    db.add(session); db.flush()
    _audit(db, session, "LIVE_SESSION_CREATED", "CREATED", "Virtual simulation session created", idempotency_key)
    db.commit()
    return _summary(db, session), True


def _allocate_scenarios(config: dict) -> dict[int, dict]:
    fleet = config["fleet"]
    total = fleet["vehicle_count"]
    revisions = ["HW_REV_A"] * fleet["hw_rev_a"] + ["HW_REV_B"] * fleet["hw_rev_b"]
    assigned: dict[int, dict] = {}
    rng = Random(config["seed"])
    for injection in config["injections"]:
        if injection["scenario"] == "nominal":
            continue
        eligible = [
            index for index, revision in enumerate(revisions)
            if index not in assigned and (
                injection["target_hardware_revision"] == "ANY"
                or revision == injection["target_hardware_revision"]
            )
        ]
        rng.shuffle(eligible)
        requested = injection.get("affected_count")
        if requested is None:
            requested = math.ceil(total * (injection.get("affected_percentage") or 0))
        for index in eligible[:requested]:
            if rng.random() <= injection["failure_probability"]:
                assigned[index] = injection
    return assigned


def _event_metrics(scenario: str, fleet: dict) -> tuple[int, int, int]:
    return (
        12 if scenario == "battery_insufficient" else fleet["average_battery"],
        10 if scenario == "network_unstable" else fleet["average_network_quality"],
        100 if scenario == "storage_insufficient" else fleet["available_storage_mb"],
    )


def _failure_path(injection: dict) -> tuple[list[str], str, bool]:
    default_step, default_error, default_rollback = DEFAULT_FAILURES[injection["scenario"]]
    step = (injection.get("installation_step") or default_step).upper()
    error = (injection.get("error_code") or default_error).upper()
    rollback = default_rollback
    if step in SUCCESS_PATH:
        states = SUCCESS_PATH[:SUCCESS_PATH.index(step) + 1]
    else:
        states = ["IDLE", "ELIGIBILITY_CHECK", step]
    states = [*states, "FAILED"]
    if rollback:
        states.extend(["ROLLBACK", "RESTORED"])
    return states, error, rollback


def start_live_session(db: Session, session_id: str, idempotency_key: str) -> dict:
    session = get_live_session(db, session_id)
    if session.start_key == idempotency_key:
        return _summary(db, session)
    if session.start_key is not None or session.status != "PREPARING":
        raise ValueError("Live simulation has already been started")
    session.start_key = idempotency_key
    session.status = "RUNNING"
    run = db.get(SimulationRun, session.simulation_id)
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == run.id, SimulationStage.stage_number == 1,
    ))
    run.status = "RUNNING"; stage.status = "RUNNING"; db.commit()
    config = session.configuration
    fleet = config["fleet"]
    assignments = _allocate_scenarios(config)
    package = db.get(SoftwarePackage, db.get(Campaign, session.campaign_id).software_package_id)
    failures = rollbacks = 0
    for index in range(fleet["vehicle_count"]):
        revision = "HW_REV_A" if index < fleet["hw_rev_a"] else "HW_REV_B"
        vehicle = Vehicle(
            vin=f"LIVE{session.id.replace('-', '')[:7].upper()}{index:06d}",
            model=fleet["model"], hardware_version=revision,
        )
        db.add(vehicle); db.flush()
        ecu = ECU(
            vehicle_id=vehicle.id, name=config["campaign"]["component"],
            hardware_version=revision, software_version=config["campaign"]["current_version"],
        )
        db.add(ecu); db.flush()
        participant = SimulationVehicle(
            simulation_id=run.id, vehicle_id=vehicle.id, ecu_id=ecu.id,
            vehicle_index=index, stage_number=1,
        )
        db.add(participant); db.flush()
        injection = assignments.get(index)
        scenario = injection["scenario"] if injection else "nominal"
        if injection:
            states, error_code, rolled_back = _failure_path(injection)
            failures += 1; rollbacks += int(rolled_back)
        else:
            states, error_code, rolled_back = SUCCESS_PATH, None, False
        battery, network, storage = _event_metrics(scenario, fleet)
        for sequence, state in enumerate(states, 1):
            created_at = datetime.now(timezone.utc)
            db.add(OTAEvent(
                event_id=str(uuid4()), timestamp=created_at, simulation_id=run.id,
                campaign_id=session.campaign_id, vehicle_id=vehicle.id, ecu_id=ecu.id,
                event_type="FAILURE" if state == "FAILED" else "STATE_CHANGE",
                installation_step=state, error_code=error_code if state == "FAILED" else None,
                software_version=package.version, hardware_revision=revision,
                battery_level=battery, network_quality=network, free_storage_mb=storage,
                attempt_number=1, sequence=sequence, stage_number=1,
                details={
                    **_trace(session), "scenario": scenario, "region": fleet["region"],
                    "temperature_c": fleet["temperature_c"],
                    "rollback_performed": state == "ROLLBACK", "created_at": created_at.isoformat(),
                },
            ))
        participant.scenario = scenario
        participant.outcome = "failure" if injection else "success"
        participant.rolled_back = rolled_back
        participant.processed_at = datetime.now(timezone.utc)
    stage.success_count = fleet["vehicle_count"] - failures
    stage.failure_count = failures
    stage.rollback_count = rollbacks
    stage.status = "COMPLETED"
    run.status = "COMPLETED"
    db.commit()
    monitoring = monitor_stage(db, run.id, 1, MonitoringThresholds(failure_rate=run.failure_threshold), anomaly_score=None)
    incident_id = monitoring["incident_id"]
    session.incident_id = incident_id
    session.status = "INCIDENT_DETECTED" if incident_id else "COMPLETED"
    session.result = {
        "vehicle_count": fleet["vehicle_count"], "success_count": stage.success_count,
        "failure_count": failures, "rollback_count": rollbacks,
        "failure_rate": failures / fleet["vehicle_count"],
        "threshold_reached": incident_id is not None,
    }
    if incident_id:
        incident = db.get(Incident, incident_id)
        incident.details = {**incident.details, **_trace(session)}
    _audit(db, session, "LIVE_SIMULATION_STARTED", "COMPLETED", "Virtual fleet simulation completed", idempotency_key)
    db.commit()
    return _summary(db, session)


def live_events(db: Session, session_id: str) -> list[dict]:
    session = get_live_session(db, session_id)
    rows = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == session.simulation_id,
    ).order_by(OTAEvent.timestamp, OTAEvent.vehicle_id, OTAEvent.sequence)))
    return [{
        "event_id": row.event_id, "timestamp": row.timestamp, "vehicle_id": row.vehicle_id,
        "event_type": row.event_type, "installation_step": row.installation_step,
        "error_code": row.error_code, "hardware_revision": row.hardware_revision,
        "battery_level": row.battery_level, "network_quality": row.network_quality,
        "free_storage_mb": row.free_storage_mb,
    } for row in rows]


def investigate_live_session(db: Session, session_id: str, idempotency_key: str) -> dict:
    session = get_live_session(db, session_id)
    if session.investigation_key == idempotency_key and session.workflow_id:
        workflow = db.get(AgenticWorkflow, session.workflow_id)
        session.status = workflow.workflow_status
        if workflow.workflow_status == "WAITING_FOR_HUMAN_APPROVAL":
            generate_automatic_report(db, workflow.id)
        _audit(
            db, session, "LIVE_INVESTIGATION_STARTED", "COMPLETED",
            f"Deterministic five-agent workflow completed: {workflow.workflow_status}",
            idempotency_key,
        )
        db.commit()
        return _summary(db, session)
    if session.investigation_key is not None:
        raise ValueError("Investigation has already been started")
    if session.status != "INCIDENT_DETECTED" or not session.incident_id:
        raise ValueError("A detected incident is required before investigation")
    session.investigation_key = idempotency_key
    session.status = "INVESTIGATING"
    workflow, _ = create_workflow(db, session.incident_id)
    session.workflow_id = workflow.id
    db.commit()
    workflow = run_workflow(db, workflow.id)
    session = get_live_session(db, session_id)
    session.status = workflow.workflow_status
    if workflow.workflow_status == "WAITING_FOR_HUMAN_APPROVAL":
        generate_automatic_report(db, workflow.id)
    _audit(
        db, session, "LIVE_INVESTIGATION_STARTED", "COMPLETED",
        f"Deterministic five-agent workflow completed: {workflow.workflow_status}",
        idempotency_key,
    )
    db.commit()
    return _summary(db, session)


def live_workflow(db: Session, session_id: str) -> dict:
    session = get_live_session(db, session_id)
    if not session.workflow_id:
        raise ValueError("Investigation has not been started")
    workflow = db.get(AgenticWorkflow, session.workflow_id)
    history = list(db.scalars(select(WorkflowHistory).where(
        WorkflowHistory.workflow_id == workflow.id,
    ).order_by(WorkflowHistory.sequence)))
    return {
        **workflow_state(workflow),
        "history": [{
            "id": row.id, "sequence": row.sequence, "agent": row.agent,
            "event_type": row.event_type, "input_summary": row.input_summary,
            "output_summary": row.output_summary, "duration_ms": row.duration_ms,
            "error_type": row.error_type, "error_message": row.error_message,
            "created_at": row.created_at,
        } for row in history],
        "source": SOURCE, "environment": ENVIRONMENT, "session_id": session.id,
    }
