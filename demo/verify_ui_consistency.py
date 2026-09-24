"""Read-only consistency audit for the AIGATOS operations interface."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(base_url: str, path: str):
    with urlopen(f"{base_url.rstrip('/')}{path}", timeout=10) as response:  # noqa: S310 - local operator URL
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--simulation-id")
    args = parser.parse_args()

    contexts = get_json(args.base_url, "/api/v1/ui/contexts?scope=all")
    if not contexts:
        raise SystemExit("Aucun contexte opérationnel n'est disponible.")
    context = next(
        (row for row in contexts if row["simulation_id"] == args.simulation_id),
        next((row for row in contexts if row["source"] == "LIVE_SIMULATION"), contexts[0]),
    )
    query = urlencode({"simulation_id": context["simulation_id"], "scope": "all"})
    dashboard = get_json(args.base_url, f"/api/v1/ui/dashboard?{query}")
    incident = get_json(args.base_url, f"/api/v1/ui/incidents/{context['incident_id']}")
    workflow = get_json(args.base_url, f"/workflows/{context['workflow_id']}")
    vehicles = get_json(
        args.base_url,
        f"/api/v1/ui/vehicles?{urlencode({'simulation_id': context['simulation_id'], 'scope': 'all', 'limit': 250})}",
    )
    audit = get_json(args.base_url, f"/api/v1/ui/audit?{urlencode({'simulation_id': context['simulation_id']})}")

    expected_counts = {
        "vehicle_count": context["vehicle_count"],
        "success_count": context["success_count"],
        "failure_count": context["failure_count"],
        "rollback_count": context["rollback_count"],
    }
    assert dashboard["active_context"]["simulation_id"] == context["simulation_id"]
    assert dashboard["tracked_vehicle_count"] == expected_counts["vehicle_count"]
    assert dashboard["success_count"] == expected_counts["success_count"]
    assert dashboard["failure_count"] == expected_counts["failure_count"]
    assert dashboard["rollback_count"] == expected_counts["rollback_count"]
    assert incident["simulation_id"] == context["simulation_id"]
    assert incident["campaign_id"] == context["campaign_id"]
    assert incident["vehicle_count"] == expected_counts["vehicle_count"]
    assert incident["success_count"] == expected_counts["success_count"]
    assert incident["failure_count"] == expected_counts["failure_count"]
    assert incident["rollback_count"] == expected_counts["rollback_count"]
    assert workflow["workflow_id"] == context["workflow_id"]
    assert workflow["incident_id"] == context["incident_id"]
    assert workflow["approval_status"] == context["approval_status"]
    assert len(workflow["evidence_ids"]) == context["evidence_count"]
    assert sum(bool(item["executed"]) for item in workflow["recommended_actions"]) == context["actions_executed"]
    assert vehicles["total"] == expected_counts["vehicle_count"]
    assert audit["context"]["context_id"] == context["context_id"]

    print(json.dumps({
        "status": "CONSISTENT",
        "simulation_id": context["simulation_id"],
        "campaign_id": context["campaign_id"],
        "incident_id": context["incident_id"],
        "workflow_id": context["workflow_id"],
        "counts": expected_counts,
        "failure_rate": context["failure_rate"],
        "evidence_count": context["evidence_count"],
        "global_confidence": context["global_confidence"],
        "workflow_status": context["workflow_status"],
        "approval_status": context["approval_status"],
        "actions_executed": context["actions_executed"],
        "audit_entries": len(audit["entries"]),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
