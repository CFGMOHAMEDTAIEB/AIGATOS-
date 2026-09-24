import hashlib
from pathlib import Path

from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import AgentEvent, AuditLog, Campaign, IncidentReport, LLMCallAudit, LiveSimulationSession, OTAEvent, SimulationStage


def jury_payload(name="BatteryManager Live Jury"):
    return {
        "created_by": "jury-operator", "seed": 20260923,
        "campaign": {
            "name": name, "component": "BatteryManager", "current_version": "2.3.0",
            "target_version": "2.4.0", "package_type": "DELTA", "package_size_mb": 128,
            "canary_strategy": "CONTROLLED_30", "failure_threshold": 0.2,
        },
        "fleet": {
            "vehicle_count": 30, "model": "AIGATOS EV", "region": "EU-LAB",
            "hw_rev_a": 27, "hw_rev_b": 3, "average_battery": 82,
            "average_network_quality": 88, "available_storage_mb": 4096,
            "temperature_c": 24,
        },
        "injections": [
            {"scenario": "hardware_software_incompatible", "affected_count": 3,
             "target_hardware_revision": "HW_REV_B", "error_code": "MEMORY_LAYOUT_MISMATCH",
             "installation_step": "MEMORY_VALIDATION", "failure_probability": 1},
            {"scenario": "battery_insufficient", "affected_count": 1,
             "target_hardware_revision": "ANY", "error_code": "BATTERY_INSUFFICIENT",
             "installation_step": "ELIGIBILITY_CHECK", "failure_probability": 1},
            {"scenario": "network_unstable", "affected_count": 1,
             "target_hardware_revision": "ANY", "error_code": "NETWORK_UNSTABLE",
             "installation_step": "DOWNLOADING", "failure_probability": 1},
            {"scenario": "storage_insufficient", "affected_count": 1,
             "target_hardware_revision": "ANY", "error_code": "STORAGE_INSUFFICIENT",
             "installation_step": "ELIGIBILITY_CHECK", "failure_probability": 1},
        ],
        "simulation_only_confirmed": True,
    }


def post(client, path, key, json=None):
    return client.post(path, json=json, headers={"Idempotency-Key": key})


def db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def test_capabilities_and_live_mode_guard(client, monkeypatch):
    capabilities = client.get("/frontend/capabilities").json()
    assert capabilities == {
        "operation_mode": "live_simulation", "can_create_simulation": True,
        "can_launch_simulation": True, "can_start_investigation": True,
        "can_review_recommendations": True, "can_execute_real_ota": False,
    }
    monkeypatch.setenv("AIGATOS_OPERATION_MODE", "readonly_demo")
    response = post(client, "/live-simulations", "readonly-key", jury_payload())
    assert response.status_code == 403


def test_validation_vehicle_limits_and_distribution(client):
    payload = jury_payload(); payload["fleet"]["vehicle_count"] = 9
    assert post(client, "/live-simulations", "invalid-size", payload).status_code == 422
    payload = jury_payload(); payload["fleet"]["hw_rev_a"] = 26
    assert post(client, "/live-simulations", "invalid-hardware", payload).status_code == 422
    assert client.post("/live-simulations", json=jury_payload()).status_code == 422


def test_validation_capacity_probability_and_nominal_rule(client):
    payload = jury_payload(); payload["injections"][0]["affected_count"] = 31
    response = post(client, "/live-simulations", "affected-over-fleet", payload)
    assert response.status_code == 422
    assert "vehicle_count" in response.text

    payload = jury_payload(); payload["injections"][0]["failure_probability"] = 75
    assert post(client, "/live-simulations", "probability-not-normalized", payload).status_code == 422

    payload = jury_payload(); payload["injections"] = [{
        "scenario": "nominal", "affected_count": 1, "target_hardware_revision": "ANY",
        "error_code": None, "installation_step": "SUCCESS", "failure_probability": 1,
    }]
    assert post(client, "/live-simulations", "invalid-nominal", payload).status_code == 422


def test_targeted_rule_sum_cannot_exceed_fleet(client):
    payload = jury_payload()
    for rule in payload["injections"]:
        rule["affected_count"] = 10
        rule["target_hardware_revision"] = "ANY"
    response = post(client, "/live-simulations", "target-sum", payload)
    assert response.status_code == 422
    assert "sum of targeted vehicles" in response.text


def test_jury_session_is_idempotent_isolated_and_runs_full_workflow(client):
    created = post(client, "/live-simulations", "create-jury-session", jury_payload())
    assert created.status_code == 201
    session = created.json()
    assert session["created"] is True and session["status"] == "PREPARING"
    assert session["source"] == "LIVE_SIMULATION" and session["environment"] == "SIMULATED"
    repeated = post(client, "/live-simulations", "create-jury-session", jury_payload()).json()
    assert repeated["id"] == session["id"] and repeated["created"] is False

    second = post(client, "/live-simulations", "create-second-session", jury_payload("Isolated Jury Session")).json()
    assert second["id"] != session["id"]
    assert second["campaign_id"] != session["campaign_id"]
    assert second["simulation_id"] != session["simulation_id"]

    started = post(client, f"/live-simulations/{session['id']}/start", "start-jury-session").json()
    assert started["status"] == "INCIDENT_DETECTED"
    assert started["result"] == {
        "vehicle_count": 30, "success_count": 24, "failure_count": 6,
        "rollback_count": 3, "failure_rate": 0.2, "threshold_reached": True,
    }
    assert started["incident_id"] and started["executed"] is False
    assert post(client, f"/live-simulations/{session['id']}/start", "start-jury-session").json()["incident_id"] == started["incident_id"]
    assert client.get(f"/live-simulations/{second['id']}").json()["status"] == "PREPARING"

    events = client.get(f"/live-simulations/{session['id']}/events").json()
    assert sum(event["event_type"] == "FAILURE" for event in events) == 6
    assert {event["error_code"] for event in events if event["error_code"]} == {
        "MEMORY_LAYOUT_MISMATCH", "BATTERY_INSUFFICIENT", "NETWORK_UNSTABLE", "STORAGE_INSUFFICIENT",
    }

    investigated = post(client, f"/live-simulations/{session['id']}/investigation", "investigate-jury-session").json()
    assert investigated["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert investigated["workflow_id"]
    workflow = client.get(f"/live-simulations/{session['id']}/workflow").json()
    assert [row["agent"] for row in workflow["history"]] == [
        "MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION",
    ]
    assert workflow["evidence_ids"]
    assert all(not action["executed"] for action in workflow["recommended_actions"])
    assert workflow["session_id"] == session["id"]

    generator, db = db_session()
    try:
        live_event_ids = set(db.scalars(select(OTAEvent.event_id).where(
            OTAEvent.simulation_id == session["simulation_id"],
        )))
        assert live_event_ids
        stage3 = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == session["simulation_id"], SimulationStage.stage_number == 3,
        ))
        assert stage3 is None
        audits = list(db.scalars(select(AuditLog).where(AuditLog.simulation_id == session["simulation_id"])))
        assert {row.action for row in audits} >= {
            "LIVE_SESSION_CREATED", "LIVE_SIMULATION_STARTED", "LIVE_INVESTIGATION_STARTED",
        }
        assert all(row.details["source"] == "LIVE_SIMULATION" for row in audits)
        report = db.scalar(select(IncidentReport).where(IncidentReport.workflow_id == investigated["workflow_id"]))
        assert report is not None and Path(report.pdf_path).is_file() and Path(report.html_path).is_file()
        assert hashlib.sha256(Path(report.pdf_path).read_bytes()).hexdigest() == report.pdf_sha256
        events = list(db.scalars(select(AgentEvent).where(AgentEvent.workflow_id == investigated["workflow_id"])))
        assert [row.event_type for row in events if row.event_type.startswith("report.")] == [
            "report.generation_started", "report.ready",
        ]
        explanation_audits = list(db.scalars(select(LLMCallAudit).where(LLMCallAudit.workflow_id == investigated["workflow_id"])))
        assert explanation_audits and all(row.attempt_count == 0 for row in explanation_audits)
    finally:
        next(generator, None)


def test_maturity_never_reaches_m5_and_live_decision_executes_nothing(client):
    session = post(client, "/live-simulations", "decision-create", jury_payload("Decision Jury Session")).json()
    post(client, f"/live-simulations/{session['id']}/start", "decision-start")
    post(client, f"/live-simulations/{session['id']}/investigation", "decision-investigate")

    maturity = client.get("/agent-maturity").json()
    assert maturity["m5_available"] is False
    assert len(maturity["agents"]) == 5
    assert all(agent["current_level"] == "M4" for agent in maturity["agents"])
    assert all(agent["criteria"]["M5"]["satisfied"] is False for agent in maturity["agents"])

    decision = post(client, f"/live-simulations/{session['id']}/decision", "decision-key", {
        "approved": True, "user": "jury-reviewer", "comment": "Simulation reviewed only",
        "timestamp": "2026-09-23T20:00:00Z", "simulation_only_confirmed": True,
    }).json()
    assert decision["decision_recorded"] is True
    assert decision["executed"] is False and decision["can_execute_real_ota"] is False
    assert decision["status"] == "HUMAN_APPROVED"
    repeated = post(client, f"/live-simulations/{session['id']}/decision", "decision-key", {
        "approved": True, "user": "jury-reviewer", "comment": "Simulation reviewed only",
        "timestamp": "2026-09-23T20:00:00Z", "simulation_only_confirmed": True,
    }).json()
    assert repeated["decision_recorded"] is True and repeated["executed"] is False


def test_operational_context_is_the_single_source_of_truth(client):
    session = post(client, "/live-simulations", "context-create", jury_payload("Operational Context")).json()
    started = post(client, f"/live-simulations/{session['id']}/start", "context-start").json()
    investigated = post(client, f"/live-simulations/{session['id']}/investigation", "context-investigate").json()

    contexts = client.get("/api/v1/ui/contexts?scope=live").json()
    context = next(row for row in contexts if row["simulation_id"] == session["simulation_id"])
    resolved = client.get(f"/api/v1/frontend/contexts/simulations/{session['simulation_id']}").json()
    dashboard = client.get(f"/api/v1/ui/dashboard?simulation_id={session['simulation_id']}&scope=all").json()
    incident = client.get(f"/api/v1/ui/incidents/{started['incident_id']}").json()
    workflow = client.get(f"/workflows/{investigated['workflow_id']}").json()
    vehicles = client.get(f"/api/v1/ui/vehicles?simulation_id={session['simulation_id']}&limit=100").json()
    audit = client.get(f"/api/v1/ui/audit?simulation_id={session['simulation_id']}").json()

    expected = {
        "vehicle_count": 30, "success_count": 24, "failure_count": 6,
        "rollback_count": 3, "failure_rate": 0.2,
    }
    assert {key: context[key] for key in expected} == expected
    assert dashboard["active_context"]["simulation_id"] == session["simulation_id"]
    assert {key: dashboard[key if key != "vehicle_count" else "tracked_vehicle_count"] for key in expected} == expected
    assert {key: incident[key] for key in expected} == expected
    assert context["incident_id"] == started["incident_id"]
    assert context["workflow_id"] == investigated["workflow_id"]
    assert context["evidence_count"] == len(workflow["evidence_ids"])
    assert context["workflow_status"] == workflow["workflow_status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert context["approval_status"] == workflow["approval_status"] == "PENDING"
    assert context["actions_executed"] == 0
    assert resolved == context
    assert vehicles["total"] == 30
    assert audit["context"]["simulation_id"] == session["simulation_id"]
    assert {entry["action"] for entry in audit["entries"]} >= {
        "LIVE_SESSION_CREATED", "LIVE_SIMULATION_STARTED", "LIVE_INVESTIGATION_STARTED", "AGENT_COMPLETED",
    }
