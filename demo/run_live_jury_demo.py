"""Run the reproducible AIGATOS live-simulation jury scenario through FastAPI.

This script never records a human decision and never calls an OTA or LLM endpoint.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"


def request(method: str, path: str, payload: dict | None = None, key: str | None = None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if key:
        headers["Idempotency-Key"] = key
    try:
        with urlopen(Request(BASE_URL + path, data=body, headers=headers, method=method), timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}: {detail}") from error


payload = {
    "created_by": "jury-operator",
    "seed": 20260923,
    "campaign": {
        "name": "AIGATOS Jury Live Simulation",
        "component": "BatteryManager",
        "current_version": "2.3.0",
        "target_version": "2.4.0",
        "package_type": "DELTA",
        "package_size_mb": 128,
        "canary_strategy": "CONTROLLED_30",
        "failure_threshold": 0.2,
    },
    "fleet": {
        "vehicle_count": 30,
        "model": "AIGATOS EV",
        "region": "EU-LAB",
        "hw_rev_a": 27,
        "hw_rev_b": 3,
        "average_battery": 82,
        "average_network_quality": 88,
        "available_storage_mb": 4096,
        "temperature_c": 24,
    },
    "injections": [
        {
            "scenario": "hardware_software_incompatible",
            "affected_count": 3,
            "target_hardware_revision": "HW_REV_B",
            "error_code": "MEMORY_LAYOUT_MISMATCH",
            "installation_step": "MEMORY_VALIDATION",
            "failure_probability": 1,
        },
        {
            "scenario": "battery_insufficient",
            "affected_count": 1,
            "target_hardware_revision": "ANY",
            "error_code": "BATTERY_INSUFFICIENT",
            "installation_step": "ELIGIBILITY_CHECK",
            "failure_probability": 1,
        },
        {
            "scenario": "network_unstable",
            "affected_count": 1,
            "target_hardware_revision": "ANY",
            "error_code": "NETWORK_UNSTABLE",
            "installation_step": "DOWNLOADING",
            "failure_probability": 1,
        },
        {
            "scenario": "storage_insufficient",
            "affected_count": 1,
            "target_hardware_revision": "ANY",
            "error_code": "STORAGE_INSUFFICIENT",
            "installation_step": "ELIGIBILITY_CHECK",
            "failure_probability": 1,
        },
    ],
    "simulation_only_confirmed": True,
}


created = request("POST", "/live-simulations", payload, "jury-live-20260923-create-v1")
session_id = created["id"]
started = request("POST", f"/live-simulations/{session_id}/start", key="jury-live-20260923-start-v1")
events = request("GET", f"/live-simulations/{session_id}/events")
investigated = request(
    "POST", f"/live-simulations/{session_id}/investigation", key="jury-live-20260923-investigation-v1"
)
workflow = request("GET", f"/live-simulations/{session_id}/workflow")
maturity = request("GET", "/agent-maturity")

assert created["source"] == "LIVE_SIMULATION"
assert created["environment"] == "SIMULATED"
assert started["result"] == {
    "vehicle_count": 30,
    "success_count": 24,
    "failure_count": 6,
    "rollback_count": 3,
    "failure_rate": 0.2,
    "threshold_reached": True,
}
assert investigated["status"] == "WAITING_FOR_HUMAN_APPROVAL"
assert [entry["agent"] for entry in workflow["history"]] == [
    "MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION"
]
assert all(action["executed"] is False for action in workflow["recommended_actions"])
assert maturity["m5_available"] is False

print(json.dumps({
    "session_id": session_id,
    "campaign_id": created["campaign_id"],
    "simulation_id": created["simulation_id"],
    "incident_id": started["incident_id"],
    "workflow_id": investigated["workflow_id"],
    "source": created["source"],
    "environment": created["environment"],
    "result": started["result"],
    "failure_events": sum(event["event_type"] == "FAILURE" for event in events),
    "workflow_status": workflow["workflow_status"],
    "approval_status": workflow["approval_status"],
    "agents": [
        {"agent": entry["agent"], "status": entry["event_type"], "duration_ms": entry["duration_ms"]}
        for entry in workflow["history"]
    ],
    "evidence_count": len(workflow["evidence_ids"]),
    "recommendations": workflow["recommended_actions"],
    "maturity": [
        {"agent": agent["agent"], "level": agent["current_level"]}
        for agent in maturity["agents"]
    ],
    "m5_available": maturity["m5_available"],
    "human_decision_recorded": False,
    "real_ota_executed": False,
}, indent=2, ensure_ascii=False))
