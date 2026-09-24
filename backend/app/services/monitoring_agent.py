"""Deterministic advisory monitoring for completed Canary simulation stages."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentEvidence, OTAEvent, SimulationRun, SimulationStage
from app.services.stage_analysis import analyze_stage


@dataclass(frozen=True)
class MonitoringThresholds:
    failure_rate: float | None = None
    rollback_rate: float | None = None
    error_code_rates: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = [self.failure_rate, self.rollback_rate, *self.error_code_rates.values()]
        if any(value is not None and not 0 <= value <= 1 for value in values):
            raise ValueError("Monitoring rates must be between 0 and 1")


def _breaches(analysis: dict, thresholds: MonitoringThresholds, configured_failure_rate: float) -> list[dict]:
    total = analysis["vehicle_count"] or 1
    failure_threshold = thresholds.failure_rate if thresholds.failure_rate is not None else configured_failure_rate
    checks = [{
        "metric": "failure_rate",
        "observed": analysis["failure"]["rate"],
        "threshold": failure_threshold,
    }]
    if thresholds.rollback_rate is not None:
        checks.append({
            "metric": "rollback_rate",
            "observed": analysis["rollback"]["rate"],
            "threshold": thresholds.rollback_rate,
        })
    for error_code, threshold in sorted(thresholds.error_code_rates.items()):
        checks.append({
            "metric": f"error_code:{error_code}",
            "observed": analysis["by_error_code"].get(error_code, 0) / total,
            "threshold": threshold,
        })
    return [check for check in checks if check["observed"] >= check["threshold"]]


def monitor_stage(
    db: Session,
    simulation_id: str,
    stage_number: int,
    thresholds: MonitoringThresholds | None = None,
    anomaly_score: float | None = None,
) -> dict:
    """Observe persisted evidence and upsert one advisory incident.

    This function never mutates Campaign, SimulationRun, or SimulationStage and
    never enqueues a task. An ML score is optional context, not a decision.
    """
    if anomaly_score is not None and not 0 <= anomaly_score <= 1:
        raise ValueError("anomaly_score must be between 0 and 1")
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise ValueError("Unknown simulation")
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == stage_number,
    ))
    if stage is None:
        raise ValueError("Unknown stage")
    analysis = analyze_stage(db, simulation_id, stage_number)
    active_thresholds = thresholds or MonitoringThresholds()
    breaches = _breaches(analysis, active_thresholds, run.failure_threshold)
    if not breaches:
        return {"analysis": analysis, "breaches": [], "incident_id": None, "evidence_count": 0}

    incident = db.scalar(select(Incident).where(
        Incident.simulation_id == simulation_id,
        Incident.stage_number == stage_number,
    ))
    primary = breaches[0]
    if incident is None:
        incident = Incident(
            simulation_id=simulation_id,
            campaign_id=run.campaign_id,
            stage_number=stage_number,
            failure_rate=analysis["failure"]["rate"],
            threshold=primary["threshold"],
            anomaly_score=anomaly_score,
            title=f"Canary stage {stage_number} monitoring threshold reached",
            details={"simulation_only": True, "advisory_only": True},
        )
        db.add(incident)
        db.flush()
    elif anomaly_score is not None:
        incident.anomaly_score = anomaly_score

    failure_vehicle_ids = set(db.scalars(select(OTAEvent.vehicle_id).where(
        OTAEvent.simulation_id == simulation_id,
        OTAEvent.stage_number == stage_number,
        OTAEvent.event_type == "FAILURE",
    )))
    evidence_events = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == simulation_id,
        OTAEvent.stage_number == stage_number,
        OTAEvent.vehicle_id.in_(failure_vehicle_ids),
    ).order_by(OTAEvent.vehicle_id, OTAEvent.sequence))) if failure_vehicle_ids else []
    existing = set(db.scalars(select(IncidentEvidence.event_id).where(
        IncidentEvidence.incident_id == incident.id,
    )))
    for event in evidence_events:
        if event.event_id not in existing:
            db.add(IncidentEvidence(incident_id=incident.id, event_id=event.event_id))
    incident.details = {
        **(incident.details or {}),
        "simulation_only": True,
        "advisory_only": True,
        "breaches": breaches,
        "counts": {
            "vehicles": analysis["vehicle_count"],
            "success": analysis["success"]["count"],
            "failure": analysis["failure"]["count"],
            "rollback": analysis["rollback"]["count"],
        },
        "by_hardware_revision": analysis["by_hardware_revision"],
        "by_error_code": analysis["by_error_code"],
        "failures_by_installation_step": analysis["failures_by_installation_step"],
        "evidence_event_count": len(evidence_events),
        "ml_score_is_advisory": anomaly_score is not None,
    }
    db.flush()
    return {
        "analysis": analysis,
        "breaches": breaches,
        "incident_id": incident.id,
        "evidence_count": len(evidence_events),
        "anomaly_score": incident.anomaly_score,
    }
