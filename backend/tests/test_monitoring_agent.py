from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.db import get_db
from app.main import app
from app.models import Campaign, Incident, IncidentEvidence, SimulationRun, SimulationStage
from app.services.monitoring_agent import MonitoringThresholds, monitor_stage
from app.services.ota_simulator import run_stage


def _create_stage_two(client, monkeypatch) -> str:
    monkeypatch.setattr(
        "app.api.simulations.simulate_stage.delay",
        lambda *_: SimpleNamespace(id="monitoring-test-task"),
    )
    package = client.post("/api/v1/software-packages", json={
        "name": "Monitoring package", "version": "3.0.0",
        "target_hardware": "HW_REV_A", "checksum_sha256": "e" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Monitoring campaign", "software_package_id": package["id"],
    }).json()
    run_id = client.post("/api/v1/simulations", json={
        "campaign_id": campaign["id"], "seed": 42,
        "hw_b_failure_probability": 1.0, "failure_threshold": 0.2,
    }).json()["id"]
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_stage(db, run_id, 1)
    finally:
        next(generator, None)
    client.post(f"/api/v1/simulations/{run_id}/stages/1/evaluate", json={
        "approved": True, "note": "Approved simulation stage for monitoring test", "reviewer": "tester",
    }).raise_for_status()
    client.post(f"/api/v1/simulations/{run_id}/advance").raise_for_status()
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_stage(db, run_id, 2)
    finally:
        next(generator, None)
    return run_id


def test_monitoring_threshold_validation():
    with pytest.raises(ValueError):
        MonitoringThresholds(failure_rate=1.1)
    with pytest.raises(ValueError):
        MonitoringThresholds(error_code_rates={"X": -0.1})


def test_monitoring_is_idempotent_and_never_advances(client, monkeypatch):
    run_id = _create_stage_two(client, monkeypatch)
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_before = db.get(SimulationRun, run_id)
        stage_two = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run_id, SimulationStage.stage_number == 2,
        ))
        stage_three = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run_id, SimulationStage.stage_number == 3,
        ))
        campaign = db.get(Campaign, run_before.campaign_id)
        before = (run_before.status, run_before.current_stage, stage_two.status, stage_three.status, campaign.status)

        first = monitor_stage(
            db, run_id, 2,
            MonitoringThresholds(error_code_rates={"MEMORY_LAYOUT_MISMATCH": 0.1}),
            anomaly_score=0.73,
        )
        second = monitor_stage(
            db, run_id, 2,
            MonitoringThresholds(error_code_rates={"MEMORY_LAYOUT_MISMATCH": 0.1}),
            anomaly_score=0.73,
        )
        db.commit()

        assert first["incident_id"] == second["incident_id"]
        assert first["evidence_count"] > 0
        assert db.scalar(select(func.count()).select_from(Incident).where(
            Incident.simulation_id == run_id, Incident.stage_number == 2,
        )) == 1
        assert db.scalar(select(func.count()).select_from(IncidentEvidence).where(
            IncidentEvidence.incident_id == first["incident_id"],
        )) == first["evidence_count"]
        incident = db.get(Incident, first["incident_id"])
        assert incident.anomaly_score == 0.73

        db.expire_all()
        run_after = db.get(SimulationRun, run_id)
        stage_two = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run_id, SimulationStage.stage_number == 2,
        ))
        stage_three = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run_id, SimulationStage.stage_number == 3,
        ))
        campaign = db.get(Campaign, run_after.campaign_id)
        after = (run_after.status, run_after.current_stage, stage_two.status, stage_three.status, campaign.status)
        assert after == before
        assert stage_three.task_id is None
    finally:
        next(generator, None)
