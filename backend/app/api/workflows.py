import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AgentEvent, AgentExecution, AgentMessage, AgenticWorkflow, HumanApprovalRequest, Incident,
    IncidentEvidence, OTAEvent, ToolExecution, WorkflowHistory,
)
from app.schemas.workflow import HumanDecision
from app.services.agentic_workflow import (
    TERMINAL_STATUSES, create_workflow, prepare_retry, record_human_decision, workflow_state,
)
from app.tasks import run_investigation


router = APIRouter(tags=["agentic-workflows"])


def _get_workflow(db: Session, workflow_id: str) -> AgenticWorkflow:
    workflow = db.get(AgenticWorkflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _enqueue(db: Session, workflow: AgenticWorkflow) -> None:
    try:
        task = run_investigation.delay(workflow.id)
        workflow.task_id = task.id
        db.commit()
    except Exception as error:
        db.rollback()
        workflow = db.get(AgenticWorkflow, workflow.id)
        workflow.workflow_status = "RETRYABLE_ERROR"
        workflow.last_error = "Investigation queue unavailable"
        db.commit()
        raise HTTPException(status_code=503, detail="Investigation queue unavailable") from error


@router.post("/incidents/{incident_id}/investigations", status_code=status.HTTP_202_ACCEPTED)
def start_investigation(incident_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        workflow, created = create_workflow(db, incident_id)
    except ValueError as error:
        raise HTTPException(status_code=404 if "Unknown" in str(error) else 409, detail=str(error)) from error
    db.commit()
    if created:
        _enqueue(db, workflow)
    return {**workflow_state(workflow), "created": created, "task_id": workflow.task_id}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)) -> dict:
    return workflow_state(_get_workflow(db, workflow_id))


@router.get("/workflows/{workflow_id}/history")
def get_history(workflow_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_workflow(db, workflow_id)
    rows = list(db.scalars(select(WorkflowHistory).where(
        WorkflowHistory.workflow_id == workflow_id,
    ).order_by(WorkflowHistory.sequence)))
    return [{
        "id": row.id, "sequence": row.sequence, "agent": row.agent,
        "event_type": row.event_type, "input_summary": row.input_summary,
        "output_summary": row.output_summary, "duration_ms": row.duration_ms,
        "error_type": row.error_type, "error_message": row.error_message,
        "created_at": row.created_at,
    } for row in rows]


@router.get("/workflows/{workflow_id}/executions")
def get_executions(workflow_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_workflow(db, workflow_id)
    rows = list(db.scalars(select(AgentExecution).where(
        AgentExecution.workflow_id == workflow_id,
    ).order_by(AgentExecution.created_at, AgentExecution.agent_type, AgentExecution.attempt)))
    return [{
        "id": row.id, "agent_type": row.agent_type, "objective": row.objective,
        "status": row.status, "current_state": row.current_state,
        "observation": row.observation, "plan": row.plan,
        "selected_tool": row.selected_tool, "tool_call_ids": row.tool_call_ids,
        "validation_result": row.validation_result, "runtime_retry_count": row.runtime_retry_count,
        "stop_reason": row.stop_reason,
        "tools_allowed": row.tools_allowed, "tools_used": row.tools_used,
        "input_payload": row.input_payload, "output_payload": row.output_payload,
        "evidence_ids": row.evidence_ids, "incoming_message_ids": row.incoming_message_ids,
        "outgoing_message_ids": row.outgoing_message_ids, "validations": row.validations,
        "attempt": row.attempt, "duration_ms": row.duration_ms,
        "proposed_next_state": row.proposed_next_state, "output_source": row.output_source,
        "llm_provider": row.llm_provider, "llm_model": row.llm_model,
        "error_code": row.error_code, "created_at": row.created_at, "completed_at": row.completed_at,
    } for row in rows]


@router.get("/workflows/{workflow_id}/messages")
def get_messages(workflow_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_workflow(db, workflow_id)
    rows = list(db.scalars(select(AgentMessage).where(
        AgentMessage.workflow_id == workflow_id,
    ).order_by(AgentMessage.sequence_number)))
    return [{
        "id": row.id, "sender_agent": row.sender_agent, "receiver_agent": row.receiver_agent,
        "message_type": row.message_type, "summary": row.summary, "payload": row.payload,
        "evidence_ids": row.evidence_ids, "tool_call_ids": row.tool_call_ids,
        "correlation_id": row.correlation_id,
        "sequence_number": row.sequence_number, "validation_status": row.validation_status,
        "created_at": row.created_at, "consumed_at": row.consumed_at,
    } for row in rows]


@router.get("/workflows/{workflow_id}/tools")
def get_tool_executions(workflow_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_workflow(db, workflow_id)
    rows = list(db.scalars(select(ToolExecution).where(
        ToolExecution.workflow_id == workflow_id,
    ).order_by(ToolExecution.created_at, ToolExecution.sequence_number)))
    return [{
        "id": row.id, "agent_execution_id": row.agent_execution_id,
        "agent_type": row.agent_type, "tool_name": row.tool_name, "mode": row.mode,
        "input_payload": row.input_payload, "output_payload": row.output_payload,
        "status": row.status, "duration_ms": row.duration_ms,
        "sequence_number": row.sequence_number, "created_at": row.created_at,
    } for row in rows]


@router.get("/workflows/{workflow_id}/events")
def get_workflow_events(
    workflow_id: str,
    after: int = 0,
    db: Session = Depends(get_db),
) -> list[dict]:
    _get_workflow(db, workflow_id)
    rows = list(db.scalars(select(AgentEvent).where(
        AgentEvent.workflow_id == workflow_id,
        AgentEvent.sequence_number > after,
    ).order_by(AgentEvent.sequence_number)))
    return [{
        "id": row.id, "event_id": row.sequence_number, "event": row.event_type,
        "data": row.payload, "created_at": row.created_at,
    } for row in rows]


@router.get("/workflows/{workflow_id}/stream")
def stream_workflow_events(
    workflow_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _get_workflow(db, workflow_id)
    try:
        cursor = max(0, int(last_event_id or 0))
    except ValueError:
        cursor = 0

    def event_stream():
        nonlocal cursor
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            rows = list(db.scalars(select(AgentEvent).where(
                AgentEvent.workflow_id == workflow_id,
                AgentEvent.sequence_number > cursor,
            ).order_by(AgentEvent.sequence_number).limit(100)))
            for row in rows:
                cursor = row.sequence_number
                yield (
                    f"id: {row.sequence_number}\n"
                    f"event: {row.event_type}\n"
                    f"data: {json.dumps(row.payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                )
            workflow = db.get(AgenticWorkflow, workflow_id)
            if workflow is None or (workflow.workflow_status in TERMINAL_STATUSES and not rows):
                return
            if not rows:
                yield ": keep-alive\n\n"
                time.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/incidents/{incident_id}/evidence")
def get_evidence(incident_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Incident, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    rows = list(db.execute(
        select(IncidentEvidence, OTAEvent)
        .join(OTAEvent, OTAEvent.event_id == IncidentEvidence.event_id)
        .where(IncidentEvidence.incident_id == incident_id)
        .order_by(OTAEvent.vehicle_id, OTAEvent.sequence)
    ))
    return [{
        "evidence_id": link.id, "evidence_type": link.evidence_type,
        "event_id": event.event_id, "vehicle_id": event.vehicle_id,
        "sequence": event.sequence, "timestamp": event.timestamp,
        "installation_step": event.installation_step, "error_code": event.error_code,
        "hardware_revision": event.hardware_revision, "software_version": event.software_version,
        "battery_level": event.battery_level, "network_quality": event.network_quality,
        "free_storage_mb": event.free_storage_mb,
    } for link, event in rows]


@router.get("/incidents/{incident_id}/hypotheses")
def get_hypotheses(incident_id: str, db: Session = Depends(get_db)) -> list[dict]:
    workflow = db.scalar(select(AgenticWorkflow).where(AgenticWorkflow.incident_id == incident_id))
    if workflow is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return workflow.hypotheses


@router.post("/workflows/{workflow_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(workflow_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        workflow = prepare_retry(db, workflow_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _enqueue(db, workflow)
    return workflow_state(workflow)


def _decision(workflow_id: str, payload: HumanDecision, approved: bool, db: Session) -> dict:
    try:
        workflow = record_human_decision(
            db, workflow_id, approved, payload.user, payload.timestamp, payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    approval = db.scalar(select(HumanApprovalRequest).where(HumanApprovalRequest.workflow_id == workflow_id))
    return {
        **workflow_state(workflow),
        "decision": approval.status,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at,
        "comment": approval.comment,
        "ota_actions_executed": 0,
    }


@router.post("/workflows/{workflow_id}/approve")
def approve(workflow_id: str, payload: HumanDecision, db: Session = Depends(get_db)) -> dict:
    return _decision(workflow_id, payload, True, db)


@router.post("/workflows/{workflow_id}/reject")
def reject(workflow_id: str, payload: HumanDecision, db: Session = Depends(get_db)) -> dict:
    return _decision(workflow_id, payload, False, db)
