from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.db import get_db
from app.main import app
from app.models import (
    AgentExecution, AgentMessage, AgenticWorkflow, Campaign, HumanApprovalRequest,
    Incident, SimulationRun, SimulationStage, ToolExecution, WorkflowHistory,
)
from app.schemas.agents import ToolInvocation
from app.services.agent_tools import AGENT_TOOLS, ToolAuthorizationError, authorize_tool, execute_stage_tool
from app.services.agentic_workflow import (
    AGENTS, EvidenceValidationError, create_workflow, prepare_retry,
    run_workflow, validate_evidence_ids, validate_hypotheses,
)
from app.services.monitoring_agent import MonitoringThresholds, monitor_stage
from app.services.ota_simulator import run_stage


def _db():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _incident_for_stage_two(client, monkeypatch) -> str:
    monkeypatch.setattr(
        "app.api.simulations.simulate_stage.delay",
        lambda *_: SimpleNamespace(id="phase-3b-simulation-task"),
    )
    package = client.post("/api/v1/software-packages", json={
        "name": "Agentic package", "version": "3.1.0",
        "target_hardware": "HW_REV_A", "checksum_sha256": "f" * 64,
    }).json()
    campaign = client.post("/api/v1/campaigns", json={
        "name": "Agentic campaign", "software_package_id": package["id"],
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
    response = client.post(f"/api/v1/simulations/{run_id}/stages/1/evaluate", json={
        "approved": True, "note": "Synthetic stage reviewed for workflow tests", "reviewer": "tester",
    })
    response.raise_for_status()
    client.post(f"/api/v1/simulations/{run_id}/advance").raise_for_status()
    generator, db = _db()
    try:
        run_stage(db, run_id, 2)
        result = monitor_stage(db, run_id, 2, MonitoringThresholds(failure_rate=0.2), anomaly_score=None)
        db.commit()
        return result["incident_id"]
    finally:
        next(generator, None)


def test_complete_five_agent_chain_is_idempotent_and_advisory(client, monkeypatch):
    incident_id = _incident_for_stage_two(client, monkeypatch)
    generator, db = _db()
    try:
        incident = db.get(Incident, incident_id)
        run = db.get(SimulationRun, incident.simulation_id)
        stage_three = db.scalar(select(SimulationStage).where(
            SimulationStage.simulation_id == run.id, SimulationStage.stage_number == 3,
        ))
        campaign = db.get(Campaign, incident.campaign_id)
        before = (run.status, run.current_stage, stage_three.status, stage_three.task_id, campaign.status)

        workflow, created = create_workflow(db, incident_id)
        db.commit()
        assert created and incident.anomaly_score is None
        def choose_secondary_tool(agent, objective, observation, allowed_tools, deterministic_tool):
            selected = "normalize_error" if agent == "LOG_ANALYSIS" else deterministic_tool
            assert selected in allowed_tools
            return ({
                "selected_tool": selected,
                "operational_summary": "Contract-tested bounded plan.",
                "expected_result": "Validated structured output.",
            }, "DETERMINISTIC_FALLBACK", None, None, None)
        monkeypatch.setattr("app.services.agentic_workflow.choose_agent_tool", choose_secondary_tool)
        completed = run_workflow(db, workflow.id)
        assert completed.workflow_status == "WAITING_FOR_HUMAN_APPROVAL"
        assert completed.current_agent is None
        assert completed.approval_status == "PENDING"
        assert completed.global_confidence is not None
        assert completed.hypotheses[0]["factor"] == "hardware_revision"
        assert completed.hypotheses[0]["level"] == "HW_REV_B"
        assert all(item["evidence_ids"] for item in completed.hypotheses)
        assert all(not action["executed"] for action in completed.recommended_actions)
        assert {action["action"] for action in completed.recommended_actions} <= {
            "PAUSE_CAMPAIGN", "EXCLUDE_INCOMPATIBLE_VEHICLES",
            "ASSIGN_CORRECTIVE_PACKAGE", "REQUEST_ADDITIONAL_INVESTIGATION",
        }
        history = list(db.scalars(select(WorkflowHistory).where(
            WorkflowHistory.workflow_id == workflow.id,
        ).order_by(WorkflowHistory.sequence)))
        assert [item.agent for item in history] == list(AGENTS)
        assert all(item.event_type == "AGENT_COMPLETED" for item in history)
        executions = list(db.scalars(select(AgentExecution).where(
            AgentExecution.workflow_id == workflow.id,
        ).order_by(AgentExecution.created_at)))
        messages = list(db.scalars(select(AgentMessage).where(
            AgentMessage.workflow_id == workflow.id,
        ).order_by(AgentMessage.sequence_number)))
        tools = list(db.scalars(select(ToolExecution).where(ToolExecution.workflow_id == workflow.id)))
        assert [item.agent_type for item in executions] == list(AGENTS)
        assert [item.sequence_number for item in messages] == [1, 2, 3, 4, 5, 6]
        assert [item.message_type for item in messages] == [
            "INCIDENT_DETECTED", "NORMALIZED_FAILURES_READY", "CORRELATIONS_READY",
            "ROOT_CAUSES_READY", "RECOMMENDATION_PROPOSED", "HUMAN_APPROVAL_REQUIRED",
        ]
        assert all(item.validation_status == "VALIDATED" for item in messages)
        assert all(item.evidence_ids for item in messages)
        assert all(item.output_source == "DETERMINISTIC_FALLBACK" for item in executions)
        assert tools and all(item.mode in {"READ_ONLY", "INTERNAL_WRITE"} for item in tools)
        assert {item.agent_type: item.tool_name for item in tools} == {
            "MONITORING": "read_simulation_metrics",
            "LOG_ANALYSIS": "normalize_error",
            "CORRELATION": "build_cohorts",
            "RCA": "rank_root_causes",
            "DECISION": "create_pending_approval",
        }
        assert all(item.status == "COMPLETED" and item.duration_ms >= 0 for item in tools)
        log_tool = next(item for item in tools if item.agent_type == "LOG_ANALYSIS")
        assert log_tool.output_payload["result"]["normalized_error_count"] == len(completed.normalized_errors)
        assert all(item.output_payload for item in tools)
        assert next(item for item in tools if item.agent_type == "DECISION").output_payload["approval_status"] == "PENDING"
        for agent in AGENTS:
            for tool_name in AGENT_TOOLS[agent]:
                _, operation_result = execute_stage_tool(
                    ToolInvocation(agent_type=agent, tool_name=tool_name),
                    db, workflow, lambda *_args: None,
                )
                assert operation_result, f"{agent}.{tool_name} returned no operation result"

        again, was_created = create_workflow(db, incident_id)
        assert not was_created and again.id == workflow.id
        run_workflow(db, workflow.id)
        assert db.scalar(select(func.count()).select_from(WorkflowHistory).where(
            WorkflowHistory.workflow_id == workflow.id,
        )) == 5
        db.expire_all()
        run = db.get(SimulationRun, incident.simulation_id)
        stage_three = db.get(SimulationStage, stage_three.id)
        campaign = db.get(Campaign, incident.campaign_id)
        assert (run.status, run.current_stage, stage_three.status, stage_three.task_id, campaign.status) == before
    finally:
        next(generator, None)


def test_resume_after_interruption_and_retry_limit(client, monkeypatch):
    incident_id = _incident_for_stage_two(client, monkeypatch)
    generator, db = _db()
    try:
        workflow, _ = create_workflow(db, incident_id)
        db.commit()

        def interrupted(*_):
            raise RuntimeError("controlled interruption")

        stopped = run_workflow(db, workflow.id, {"LOG_ANALYSIS": interrupted})
        assert stopped.workflow_status == "RETRYABLE_ERROR"
        assert stopped.current_agent == "LOG_ANALYSIS"
        assert stopped.retry_count == 1
        prepare_retry(db, workflow.id)
        resumed = run_workflow(db, workflow.id)
        assert resumed.workflow_status == "WAITING_FOR_HUMAN_APPROVAL"
        monitoring_count = db.scalar(select(func.count()).select_from(WorkflowHistory).where(
            WorkflowHistory.workflow_id == workflow.id,
            WorkflowHistory.agent == "MONITORING",
            WorkflowHistory.event_type == "AGENT_COMPLETED",
        ))
        assert monitoring_count == 1

        # A zero-second policy deterministically exercises timeout and retry caps.
        resumed.workflow_status = "QUEUED"
        resumed.current_agent = "MONITORING"
        resumed.agent_timeout_seconds = 0
        resumed.retry_count = resumed.max_retries - 1
        db.commit()
        timed_out = run_workflow(db, resumed.id)
        assert timed_out.workflow_status == "FAILED"
        assert timed_out.retry_count == timed_out.max_retries
        assert "timeout" in timed_out.last_error.lower()
        with pytest.raises(ValueError):
            prepare_retry(db, resumed.id)
    finally:
        next(generator, None)


def test_invalid_evidence_and_unproven_hypothesis_are_rejected(client, monkeypatch):
    incident_id = _incident_for_stage_two(client, monkeypatch)
    generator, db = _db()
    try:
        workflow, _ = create_workflow(db, incident_id)
        db.commit()
        with pytest.raises(EvidenceValidationError):
            validate_evidence_ids(db, incident_id, ["00000000-0000-0000-0000-000000000000"])
        workflow.hypotheses = [{"statement": "unsupported", "evidence_ids": []}]
        with pytest.raises(EvidenceValidationError):
            validate_hypotheses(db, workflow)
    finally:
        next(generator, None)


def test_human_endpoint_requires_timestamp_and_is_idempotent(client, monkeypatch):
    incident_id = _incident_for_stage_two(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.workflows.run_investigation.delay",
        lambda *_: SimpleNamespace(id="phase-3b-investigation-task"),
    )
    started = client.post(f"/incidents/{incident_id}/investigations")
    assert started.status_code == 202
    workflow_id = started.json()["workflow_id"]
    generator, db = _db()
    try:
        run_workflow(db, workflow_id)
    finally:
        next(generator, None)

    payload = {
        "user": "safety-reviewer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "comment": "Reviewed in a synthetic test; no OTA action authorized.",
    }
    assert client.post(f"/workflows/{workflow_id}/approve", json={
        "user": payload["user"], "comment": payload["comment"],
    }).status_code == 422
    first = client.post(f"/workflows/{workflow_id}/approve", json=payload)
    second = client.post(f"/workflows/{workflow_id}/approve", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["ota_actions_executed"] == 0
    assert second.json()["decision"] == "APPROVED"
    assert client.post(f"/workflows/{workflow_id}/reject", json=payload).status_code == 409
    generator, db = _db()
    try:
        assert db.scalar(select(func.count()).select_from(HumanApprovalRequest).where(
            HumanApprovalRequest.workflow_id == workflow_id,
        )) == 1
        assert db.scalar(select(func.count()).select_from(WorkflowHistory).where(
            WorkflowHistory.workflow_id == workflow_id,
            WorkflowHistory.event_type == "HUMAN_DECISION",
        )) == 1
    finally:
        next(generator, None)


def test_phase_3b_has_no_llm_or_operational_model_dependency():
    source = (Path(__file__).parents[1] / "app/services/agentic_workflow.py").read_text(encoding="utf-8").lower()
    forbidden_imports = ("import openai", "import langgraph", "import joblib", "from ml", "from sklearn")
    assert not any(value in source for value in forbidden_imports)
    assert "anomaly_score is not none" in source


def test_tool_registry_rejects_cross_agent_invocation():
    with pytest.raises(ToolAuthorizationError):
        authorize_tool(ToolInvocation(
            agent_type="DECISION", tool_name="calculate_risk_ratio", input_payload={},
        ))
