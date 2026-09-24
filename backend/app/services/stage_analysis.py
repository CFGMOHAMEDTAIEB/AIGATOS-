from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OTAEvent, SimulationRun, SimulationStage, SimulationVehicle, Vehicle


def analyze_stage(db: Session, simulation_id: str, stage_number: int) -> dict:
    """Build a deterministic evidence summary exclusively from persisted rows."""
    run = db.get(SimulationRun, simulation_id)
    if run is None:
        raise ValueError("Unknown simulation")
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == stage_number,
    ))
    if stage is None:
        raise ValueError("Unknown stage")

    participants = list(db.execute(
        select(SimulationVehicle, Vehicle.hardware_version)
        .join(Vehicle, Vehicle.id == SimulationVehicle.vehicle_id)
        .where(
            SimulationVehicle.simulation_id == simulation_id,
            SimulationVehicle.stage_number == stage_number,
        )
        .order_by(SimulationVehicle.vehicle_index)
    ))
    failure_events = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == simulation_id,
        OTAEvent.stage_number == stage_number,
        OTAEvent.event_type == "FAILURE",
    )))
    events = list(db.scalars(select(OTAEvent).where(
        OTAEvent.simulation_id == simulation_id,
        OTAEvent.stage_number == stage_number,
    ).order_by(OTAEvent.vehicle_id, OTAEvent.sequence)))
    step_counts = Counter(event.installation_step for event in events)
    failure_steps = Counter()
    previous_step_by_vehicle: dict[str, str] = {}
    for event in events:
        if event.event_type == "FAILURE":
            previous = previous_step_by_vehicle.get(event.vehicle_id)
            if previous:
                failure_steps[previous] += 1
        previous_step_by_vehicle[event.vehicle_id] = event.installation_step
    hardware = Counter()
    for participant, revision in participants:
        outcome = participant.outcome if participant.outcome is not None else "pending"
        outcome = "success" if outcome == "success" else ("failure" if outcome == "restored" else "pending")
        hardware[(revision, outcome)] += 1

    total = stage.vehicle_count
    rate = lambda count: count / total if total else 0.0
    error_counts = Counter(event.error_code for event in failure_events if event.error_code)
    return {
        "simulation_id": simulation_id,
        "stage_number": stage_number,
        "status": stage.status,
        "vehicle_count": total,
        "processed_count": sum(participant.processed_at is not None for participant, _ in participants),
        "success": {"count": stage.success_count, "rate": rate(stage.success_count)},
        "failure": {"count": stage.failure_count, "rate": rate(stage.failure_count)},
        "rollback": {"count": stage.rollback_count, "rate": rate(stage.rollback_count)},
        "failure_threshold": run.failure_threshold,
        "threshold_reached": rate(stage.failure_count) >= run.failure_threshold,
        "by_hardware_revision": {
            revision: {
                "success": hardware[(revision, "success")],
                "failure": hardware[(revision, "failure")],
                "pending": hardware[(revision, "pending")],
            }
            for revision in sorted({revision for _, revision in participants})
        },
        "by_error_code": dict(sorted(error_counts.items())),
        "by_installation_step": dict(sorted(step_counts.items())),
        "failures_by_installation_step": dict(sorted(failure_steps.items())),
        "focus": {
            "HW_REV_B": {
                "success": hardware[("HW_REV_B", "success")],
                "failure": hardware[("HW_REV_B", "failure")],
            },
            "MEMORY_LAYOUT_MISMATCH": error_counts["MEMORY_LAYOUT_MISMATCH"],
            "MEMORY_VALIDATION": {
                "event_count": step_counts["MEMORY_VALIDATION"],
                "failure_count": failure_steps["MEMORY_VALIDATION"],
            },
        },
    }
