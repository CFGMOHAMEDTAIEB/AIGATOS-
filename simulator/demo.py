"""Command-line demo for the advisory OTA simulator.

Each evaluation and advance is a separate, explicit command.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import SimulationVehicle
from app.services.stage_analysis import analyze_stage


def emit(value):
    print(json.dumps(value, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="AIGATOS phase 2 demo")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--seed", type=int, default=42)
    start.add_argument("--probability", type=float, default=0.9)
    status = sub.add_parser("status")
    status.add_argument("run_id")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("run_id")
    evaluate.add_argument("stage", type=int)
    evaluate.add_argument("--approve", action="store_true")
    evaluate.add_argument("--note", required=True)
    evaluate.add_argument("--reviewer", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("run_id")
    report = sub.add_parser("report")
    report.add_argument("run_id")
    report.add_argument("--stage", type=int, choices=(1, 2, 3))
    args = parser.parse_args()

    with TestClient(app) as client:
        if args.command == "start":
            packages = client.get("/api/v1/software-packages", params={"limit": 100}).json()
            package = next((p for p in packages if p["name"] == "BatteryManager" and p["version"] == "2.4.0"), None)
            if package is None:
                response = client.post("/api/v1/software-packages", json={
                    "name": "BatteryManager", "version": "2.4.0",
                    "target_hardware": "HW_REV_A", "checksum_sha256": "b" * 64,
                })
                response.raise_for_status()
                package = response.json()
            name = "BatteryManager 2.4.0 demo " + uuid4().hex[:8]
            response = client.post("/api/v1/campaigns", json={
                "name": name, "software_package_id": package["id"],
                "canary_percentage": 10,
            })
            response.raise_for_status()
            campaign = response.json()
            response = client.post("/api/v1/simulations", json={
                "campaign_id": campaign["id"], "seed": args.seed,
                "hw_b_failure_probability": args.probability,
            })
        elif args.command == "status":
            response = client.get(f"/api/v1/simulations/{args.run_id}")
        elif args.command == "evaluate":
            response = client.post(
                f"/api/v1/simulations/{args.run_id}/stages/{args.stage}/evaluate",
                json={"approved": args.approve, "note": args.note, "reviewer": args.reviewer},
            )
        elif args.command == "advance":
            response = client.post(f"/api/v1/simulations/{args.run_id}/advance")
        else:
            response = client.get(f"/api/v1/simulations/{args.run_id}")
        response.raise_for_status()
        data = response.json()
        if args.command == "report":
            with SessionLocal() as db:
                participants = list(db.scalars(select(SimulationVehicle).where(
                    SimulationVehicle.simulation_id == args.run_id,
                )))
                if args.stage is not None:
                    data["stage_analysis"] = analyze_stage(db, args.run_id, args.stage)
            data["totals"] = {
                "vehicles": len(participants),
                "processed": sum(p.outcome is not None for p in participants),
                "successes": sum(p.outcome == "success" for p in participants),
                "failures": sum(p.outcome == "restored" for p in participants),
                "rollbacks": sum(p.rolled_back for p in participants),
                "scenarios": dict(Counter(p.scenario for p in participants if p.scenario)),
            }
        emit(data)


if __name__ == "__main__":
    main()
