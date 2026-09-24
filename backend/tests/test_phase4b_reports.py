import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import (
    AgenticWorkflow, Campaign, Incident, IncidentExplanation, SimulationRun,
    SimulationStage,
)
from app.services.agentic_workflow import create_workflow, run_workflow
from app.services.incident_report import (
    ReportValidationError, collect_report_data, generate_report, render_pdf,
)
from app.services.monitoring_agent import MonitoringThresholds, monitor_stage
from app.services.ota_simulator import run_stage


def _db():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _case(client, monkeypatch):
    monkeypatch.setattr("app.api.simulations.simulate_stage.delay", lambda *_: SimpleNamespace(id="p4b"))
    package = client.post("/api/v1/software-packages", json={
        "name": "BatteryManager", "version": "2.4.0", "target_hardware": "HW_REV_A",
        "checksum_sha256": "c" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Phase 4B test", "software_package_id": package["id"],
    }).json()
    run_id = client.post("/api/v1/simulations", json={
        "campaign_id": campaign["id"], "seed": 42,
        "hw_b_failure_probability": 1.0, "failure_threshold": 0.2,
    }).json()["id"]
    generator, db = _db()
    try:
        run_stage(db, run_id, 1)
    finally:
        next(generator, None)
    client.post(f"/api/v1/simulations/{run_id}/stages/1/evaluate", json={
        "approved": True, "note": "Synthetic report prerequisite reviewed", "reviewer": "tester",
    }).raise_for_status()
    client.post(f"/api/v1/simulations/{run_id}/advance").raise_for_status()
    generator, db = _db()
    try:
        run_stage(db, run_id, 2)
        incident_id = monitor_stage(db, run_id, 2, MonitoringThresholds(failure_rate=0.2), anomaly_score=None)["incident_id"]
        db.commit()
        workflow, _ = create_workflow(db, incident_id); db.commit(); run_workflow(db, workflow.id)
        top = workflow.hypotheses[0]
        explanation = IncidentExplanation(
            workflow_id=workflow.id, incident_id=incident_id, input_hash="d" * 64,
            provider="nvidia", model_name="z-ai/glm-5.3", prompt_version="phase4a-v1",
            source="DETERMINISTIC_FALLBACK", status="FALLBACK_TIMEOUT", duration_ms=30000,
            output={
                "incident_summary": "30 vehicles: 24 succeeded and 6 failed.",
                "probable_root_cause": "Probable HW_REV_B and package incompatibility.",
                "confidence_interpretation": "The unchanged deterministic score is 0.620644.",
                "evidence_citations": [{"evidence_id": value, "statement": "Validated evidence."} for value in top["evidence_ids"]],
                "alternative_hypotheses": [item["statement"] for item in workflow.hypotheses[1:]],
                "recommended_next_steps": [item["action"] for item in workflow.recommended_actions],
                "limitations": ["Correlation does not prove causality."],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model_name": "z-ai/glm-5.3", "prompt_version": "phase4a-v1",
            },
        )
        db.add(explanation); db.commit()
        return workflow.id, incident_id, explanation.id, run_id
    finally:
        next(generator, None)


def test_report_is_safe_idempotent_and_preserves_invariants(client, monkeypatch, tmp_path):
    workflow_id, incident_id, explanation_id, run_id = _case(client, monkeypatch)
    generator, db = _db()
    try:
        workflow = db.get(AgenticWorkflow, workflow_id)
        incident = db.get(Incident, incident_id)
        run = db.get(SimulationRun, run_id)
        campaign = db.get(Campaign, incident.campaign_id)
        stage3 = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run_id, SimulationStage.stage_number == 3,
        ))
        before = (workflow.workflow_status, workflow.approval_status, campaign.status, run.current_stage, stage3.status, stage3.task_id)
        monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-report-secret-never-output")
        explanation = db.get(IncidentExplanation, explanation_id)
        output = dict(explanation.output)
        output["incident_summary"] = "<script>alert('injection')</script> 30 vehicles reviewed."
        explanation.output = output; db.commit()

        report, cached = generate_report(db, workflow_id, incident_id, explanation_id, tmp_path)
        again, second_cached = generate_report(db, workflow_id, incident_id, explanation_id, tmp_path)
        assert not cached and second_cached and again.id == report.id
        pdf_bytes = Path(report.pdf_path).read_bytes()
        html_text = Path(report.html_path).read_text(encoding="utf-8")
        assert hashlib.sha256(pdf_bytes).hexdigest() == report.pdf_sha256
        assert "<script>" not in html_text and "&lt;script&gt;" in html_text
        assert "synthetic-report-secret-never-output" not in html_text
        assert "synthetic-report-secret-never-output".encode() not in pdf_bytes
        assert "0.620644" in html_text and "executed</th>" in html_text
        assert all(not item["executed"] for item in workflow.recommended_actions)
        text = "\n".join(page.extract_text() or "" for page in PdfReader(report.pdf_path).pages)
        for evidence_id in explanation.output["evidence_citations"]:
            assert evidence_id["evidence_id"] in text
        assert "DETERMINISTIC_FALLBACK" in text

        db.expire_all(); workflow = db.get(AgenticWorkflow, workflow_id); run = db.get(SimulationRun, run_id)
        campaign = db.get(Campaign, incident.campaign_id); stage3 = db.get(SimulationStage, stage3.id)
        after = (workflow.workflow_status, workflow.approval_status, campaign.status, run.current_stage, stage3.status, stage3.task_id)
        assert after == before == ("WAITING_FOR_HUMAN_APPROVAL", "PENDING", "draft", 2, "pending", None)
    finally:
        next(generator, None)


def test_pdf_hash_is_reproducible_and_unknown_incident_rejected(client, monkeypatch, tmp_path):
    workflow_id, incident_id, explanation_id, _ = _case(client, monkeypatch)
    generator, db = _db()
    try:
        data = collect_report_data(db, workflow_id, incident_id, explanation_id)
        generated_at = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        first = tmp_path / "first.pdf"
        render_pdf(first, data, generated_at, 1)
        first_hash = hashlib.sha256(first.read_bytes()).digest()
        assert first_hash == hashlib.sha256(first.read_bytes()).digest()
        with pytest.raises(ReportValidationError, match="not found"):
            collect_report_data(db, workflow_id, "00000000-0000-0000-0000-000000000000", explanation_id)
    finally:
        next(generator, None)


def test_report_endpoint_rejects_unknown_incident(client):
    response = client.post("/incidents/00000000-0000-0000-0000-000000000000/reports", json={
        "workflow_id": "00000000-0000-0000-0000-000000000001",
        "explanation_id": "00000000-0000-0000-0000-000000000002",
    })
    assert response.status_code == 404
