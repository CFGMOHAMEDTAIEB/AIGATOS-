from datetime import datetime, timezone
from hashlib import sha256
from random import Random
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, ECU, Incident, OTAEvent, SimulationRun, SimulationStage, SimulationVehicle, Vehicle
from app.schemas.simulation import OTAEventData

STAGE_SIZES = (10, 30, 60)
SUCCESS_STATES = (
    "IDLE", "ELIGIBILITY_CHECK", "DOWNLOADING", "VERIFYING_PACKAGE",
    "INSTALLING", "MEMORY_VALIDATION", "REBOOTING", "HEALTH_CHECK", "SUCCESS",
)
FAILURES = {
    "battery_low": ("ELIGIBILITY_CHECK", "BATTERY_INSUFFICIENT"),
    "network_unstable": ("DOWNLOADING", "NETWORK_UNSTABLE"),
    "storage_low": ("ELIGIBILITY_CHECK", "STORAGE_INSUFFICIENT"),
    "package_corrupt": ("VERIFYING_PACKAGE", "PACKAGE_CORRUPTED"),
    "hardware_incompatible": ("MEMORY_VALIDATION", "MEMORY_LAYOUT_MISMATCH"),
    "ecu_unresponsive": ("REBOOTING", "ECU_NOT_RESPONDING"),
    "installation_failure": ("INSTALLING", "INSTALLATION_FAILED"),
}
FIXED_SCENARIOS = {
    11: "battery_low", 21: "network_unstable", 31: "storage_low",
    41: "package_corrupt", 61: "ecu_unresponsive", 81: "installation_failure",
}


def stage_for_index(index: int) -> int:
    if not 0 <= index < 100:
        raise ValueError("vehicle index must be 0..99")
    return 1 if index < 10 else (2 if index < 40 else 3)


def scenario_for(seed: int, index: int, hw_b_failure_probability: float) -> str:
    if index % 10 == 0:
        digest = sha256(f"{seed}:{index}".encode("ascii")).digest()
        return "hardware_incompatible" if Random(int.from_bytes(digest, "big")).random() < hw_b_failure_probability else "success"
    return FIXED_SCENARIOS.get(index, "success")


def state_path(scenario: str) -> tuple[list[str], str | None, bool]:
    if scenario == "success":
        return list(SUCCESS_STATES), None, False
    fail_state, error_code = FAILURES[scenario]
    states = list(SUCCESS_STATES[:SUCCESS_STATES.index(fail_state) + 1])
    states.extend(("FAILED", "ROLLBACK", "RESTORED"))
    rollback_performed = SUCCESS_STATES.index(fail_state) >= SUCCESS_STATES.index("INSTALLING")
    return states, error_code, rollback_performed


def event_metrics(scenario: str) -> tuple[int, int, int]:
    return (
        12 if scenario == "battery_low" else 82,
        10 if scenario == "network_unstable" else 88,
        100 if scenario == "storage_low" else 4096,
    )


def provision_vehicles(db: Session, run: SimulationRun) -> None:
    exists = db.scalar(select(SimulationVehicle.id).where(SimulationVehicle.simulation_id == run.id).limit(1))
    if exists:
        return
    for index in range(100):
        revision = "HW_REV_B" if index % 10 == 0 else "HW_REV_A"
        vehicle = Vehicle(
            vin=f"AGT{run.id.replace('-', '')[:8].upper()}{index:06d}",
            model="AIGATOS_SIM", hardware_version=revision,
        )
        db.add(vehicle)
        db.flush()
        ecu = ECU(
            vehicle_id=vehicle.id, name="BatteryManager",
            hardware_version=revision, software_version="2.3.0",
        )
        db.add(ecu)
        db.flush()
        db.add(SimulationVehicle(
            simulation_id=run.id, vehicle_id=vehicle.id, ecu_id=ecu.id,
            vehicle_index=index, stage_number=stage_for_index(index),
        ))
    db.commit()


def simulate_vehicle(db: Session, run: SimulationRun, participant: SimulationVehicle, software_version: str) -> None:
    if participant.processed_at is not None:
        return
    vehicle = db.get(Vehicle, participant.vehicle_id)
    scenario = scenario_for(run.seed, participant.vehicle_index, run.hw_b_failure_probability)
    states, error_code, rolled_back = state_path(scenario)
    battery, network, storage = event_metrics(scenario)
    for sequence, state in enumerate(states, 1):
        event = OTAEventData(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            simulation_id=run.id,
            campaign_id=run.campaign_id,
            vehicle_id=participant.vehicle_id,
            ecu_id=participant.ecu_id,
            event_type="FAILURE" if state == "FAILED" else "STATE_CHANGE",
            installation_step=state,
            error_code=error_code if state == "FAILED" else None,
            software_version=software_version,
            hardware_revision=vehicle.hardware_version,
            battery_level=battery,
            network_quality=network,
            free_storage_mb=storage,
            attempt_number=1,
            metadata={
                "scenario": scenario,
                "advisory_only": True,
                "rollback_performed": rolled_back if state == "ROLLBACK" else False,
            },
            sequence=sequence,
            stage_number=participant.stage_number,
        )
        values = event.model_dump()
        values["details"] = values.pop("metadata")
        db.add(OTAEvent(**values))
    participant.scenario = scenario
    participant.outcome = "success" if scenario == "success" else "restored"
    participant.rolled_back = rolled_back
    participant.processed_at = datetime.now(timezone.utc)
    db.commit()


def ensure_failure_incident(db: Session, run: SimulationRun, stage: SimulationStage) -> Incident | None:
    """Create the threshold incident once, including for safely replayed analysis."""
    failure_rate = stage.failure_count / stage.vehicle_count if stage.vehicle_count else 0.0
    if failure_rate < run.failure_threshold:
        return None
    incident = db.scalar(select(Incident).where(
        Incident.simulation_id == run.id,
        Incident.stage_number == stage.stage_number,
    ))
    if incident is None:
        incident = Incident(
            simulation_id=run.id, campaign_id=run.campaign_id, stage_number=stage.stage_number,
            failure_rate=failure_rate, threshold=run.failure_threshold,
            title=f"Canary stage {stage.stage_number} failure threshold reached",
            details={
                "success_count": stage.success_count, "failure_count": stage.failure_count,
                "rollback_count": stage.rollback_count, "simulation_only": True,
            },
        )
        db.add(incident)
        db.flush()
    return incident


def run_stage(db: Session, simulation_id: str, stage_number: int) -> None:
    run = db.get(SimulationRun, simulation_id)
    if run is None or run.current_stage != stage_number:
        raise ValueError("Unknown simulation or stage")
    stage = db.scalar(select(SimulationStage).where(
        SimulationStage.simulation_id == simulation_id,
        SimulationStage.stage_number == stage_number,
    ))
    if stage is None or stage.status != "queued":
        raise ValueError("Stage is not queued")
    stage.status = "running"
    run.status = "running"
    db.commit()
    try:
        if stage_number == 1:
            provision_vehicles(db, run)
        campaign = db.get(Campaign, run.campaign_id)
        version = campaign.software_package.version
        participants = list(db.scalars(select(SimulationVehicle).where(
            SimulationVehicle.simulation_id == simulation_id,
            SimulationVehicle.stage_number == stage_number,
        ).order_by(SimulationVehicle.vehicle_index)))
        if len(participants) != stage.vehicle_count:
            raise RuntimeError("Stage cohort size mismatch")
        for participant in participants:
            simulate_vehicle(db, run, participant, version)
        db.refresh(stage)
        stage.success_count = sum(p.outcome == "success" for p in participants)
        stage.failure_count = sum(p.outcome != "success" for p in participants)
        stage.rollback_count = sum(p.rolled_back for p in participants)
        ensure_failure_incident(db, run, stage)
        stage.status = "awaiting_evaluation"
        run.status = "awaiting_evaluation"
        db.commit()
    except Exception:
        db.rollback()
        stage = db.get(SimulationStage, stage.id)
        run = db.get(SimulationRun, simulation_id)
        stage.status = "failed"
        run.status = "failed"
        db.commit()
        raise
