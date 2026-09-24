from collections import Counter
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import Incident, SimulationVehicle
from app.services.ota_simulator import scenario_for, stage_for_index, state_path, run_stage
from app.services.stage_analysis import analyze_stage


def test_deterministic_cohort_and_state_machine():
    a = [scenario_for(42, index, 0.9) for index in range(100)]
    b = [scenario_for(42, index, 0.9) for index in range(100)]
    assert a == b
    assert sum(stage_for_index(i) == 1 for i in range(100)) == 10
    assert sum(stage_for_index(i) == 2 for i in range(100)) == 30
    assert sum(stage_for_index(i) == 3 for i in range(100)) == 60
    assert set(a) == {
        "success", "battery_low", "network_unstable", "storage_low",
        "package_corrupt", "hardware_incompatible", "ecu_unresponsive",
        "installation_failure",
    }
    assert Counter(a)["hardware_incompatible"] >= 7
    assert all(scenario_for(42, i, 0) == "success" for i in range(0, 100, 10))
    assert all(scenario_for(42, i, 1) == "hardware_incompatible" for i in range(0, 100, 10))
    states, code, rollback = state_path("hardware_incompatible")
    assert states[-4:] == ["MEMORY_VALIDATION", "FAILED", "ROLLBACK", "RESTORED"]
    assert code == "MEMORY_LAYOUT_MISMATCH"
    assert rollback is True
    success, code, rollback = state_path("success")
    assert success[-1] == "SUCCESS"
    assert code is None and rollback is False


def test_simulation_api_manual_canary_and_timeline(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulations.simulate_stage.delay",
        lambda *_: SimpleNamespace(id="test-task"),
    )
    package = client.post("/api/v1/software-packages", json={
        "name": "BatteryManager", "version": "2.4.0",
        "target_hardware": "HW_REV_A", "checksum_sha256": "b" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Phase 2 test", "software_package_id": package["id"],
    }).json()
    launch = client.post("/api/v1/simulations", json={
        "campaign_id": campaign["id"], "seed": 42,
        "hw_b_failure_probability": 0.9,
    })
    assert launch.status_code == 202, launch.text
    run_id = launch.json()["id"]
    assert launch.json()["stages"][0]["status"] == "queued"
    assert client.post(f"/api/v1/simulations/{run_id}/advance").status_code == 409

    def execute_stage(number):
        generator = app.dependency_overrides[get_db]()
        db = next(generator)
        try:
            run_stage(db, run_id, number)
        finally:
            next(generator, None)

    execute_stage(1)
    first = client.get(f"/api/v1/simulations/{run_id}").json()
    assert first["status"] == "awaiting_evaluation"
    assert sum(first["stages"][0][k] for k in ("success_count", "failure_count")) == 10
    assert first["stages"][1]["status"] == "pending"
    assert client.post(f"/api/v1/simulations/{run_id}/advance").status_code == 409
    assert client.post(f"/api/v1/simulations/{run_id}/stages/1/evaluate", json={
        "approved": True, "note": "Results reviewed for stage one", "reviewer": "tester",
    }).status_code == 200
    assert client.get(f"/api/v1/simulations/{run_id}").json()["stages"][1]["status"] == "pending"

    for current, next_stage in ((1, 2), (2, 3)):
        advanced = client.post(f"/api/v1/simulations/{run_id}/advance")
        assert advanced.status_code == 202
        assert advanced.json()["current_stage"] == next_stage
        execute_stage(next_stage)
        if next_stage == 2:
            client.post(f"/api/v1/simulations/{run_id}/stages/2/evaluate", json={
                "approved": True, "note": "Results reviewed for stage two", "reviewer": "tester",
            }).raise_for_status()

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        participants = list(db.scalars(select(SimulationVehicle).where(
            SimulationVehicle.simulation_id == run_id,
        )))
        assert len(participants) == 100
        assert len({p.ecu_id for p in participants}) == 100
        hw_b = next(p for p in participants if p.scenario == "hardware_incompatible")
        vehicle_id = hw_b.vehicle_id
    finally:
        next(generator, None)
    timeline = client.get(f"/api/v1/simulations/{run_id}/vehicles/{vehicle_id}/timeline")
    assert timeline.status_code == 200
    data = timeline.json()
    assert [e["installation_step"] for e in data][-4:] == [
        "MEMORY_VALIDATION", "FAILED", "ROLLBACK", "RESTORED",
    ]
    assert next(e for e in data if e["installation_step"] == "FAILED")["error_code"] == "MEMORY_LAYOUT_MISMATCH"
    assert all(e["metadata"]["advisory_only"] for e in data)
    assert client.post(f"/api/v1/simulations/{run_id}/stages/3/evaluate", json={
        "approved": True, "note": "Final stage reviewed", "reviewer": "tester",
    }).json()["status"] == "completed"
    assert client.post(f"/api/v1/simulations/{run_id}/advance").status_code == 409
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()["status"] == "draft"


def test_rejected_stage_cannot_advance(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulations.simulate_stage.delay",
        lambda *_: SimpleNamespace(id="test-task-reject"),
    )
    package = client.post("/api/v1/software-packages", json={
        "name": "BatteryManager", "version": "2.4.0",
        "target_hardware": "HW_REV_A", "checksum_sha256": "c" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Rejected canary", "software_package_id": package["id"],
    }).json()
    run = client.post("/api/v1/simulations", json={
        "campaign_id": campaign["id"], "seed": 9,
    }).json()
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_stage(db, run["id"], 1)
    finally:
        next(generator, None)
    response = client.post(f"/api/v1/simulations/{run['id']}/stages/1/evaluate", json={
        "approved": False, "note": "Failure rate not acceptable",
        "reviewer": "tester",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["stages"][0]["evaluated_by"] == "tester"
    assert client.post(f"/api/v1/simulations/{run['id']}/advance").status_code == 409
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()["status"] == "draft"


def test_stage_two_analysis_stops_before_stage_three(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulations.simulate_stage.delay",
        lambda *_: SimpleNamespace(id="test-task-stage-two"),
    )
    package = client.post("/api/v1/software-packages", json={
        "name": "Stage analysis", "version": "2.4.0",
        "target_hardware": "HW_REV_A", "checksum_sha256": "d" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Stage two stop", "software_package_id": package["id"],
    }).json()
    run_id = client.post("/api/v1/simulations", json={
        "campaign_id": campaign["id"], "seed": 42,
        "hw_b_failure_probability": 1, "failure_threshold": 0.2,
    }).json()["id"]

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_stage(db, run_id, 1)
    finally:
        next(generator, None)
    client.post(f"/api/v1/simulations/{run_id}/stages/1/evaluate", json={
        "approved": True, "note": "Human approval for simulation only", "reviewer": "tester",
    }).raise_for_status()
    client.post(f"/api/v1/simulations/{run_id}/advance").raise_for_status()

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        run_stage(db, run_id, 2)
        analysis = analyze_stage(db, run_id, 2)
    finally:
        next(generator, None)

    assert analysis["vehicle_count"] == analysis["processed_count"] == 30
    assert analysis["focus"]["HW_REV_B"] == {"success": 0, "failure": 3}
    assert analysis["focus"]["MEMORY_LAYOUT_MISMATCH"] == 3
    assert analysis["focus"]["MEMORY_VALIDATION"] == {"event_count": 27, "failure_count": 3}
    assert analysis["failures_by_installation_step"] == {
        "DOWNLOADING": 1, "ELIGIBILITY_CHECK": 2, "MEMORY_VALIDATION": 3,
    }
    state = client.get(f"/api/v1/simulations/{run_id}").json()
    assert state["current_stage"] == 2
    assert state["stages"][2]["status"] == "pending"

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        incident = db.scalar(select(Incident).where(
            Incident.simulation_id == run_id, Incident.stage_number == 2,
        ))
        assert incident is not None
        assert incident.failure_rate == incident.threshold == 0.2
    finally:
        next(generator, None)
