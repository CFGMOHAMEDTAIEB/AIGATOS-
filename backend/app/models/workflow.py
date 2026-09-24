"""Persistent models for the Phase 3B agentic workflow."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.entities import utc_now
from app.models.simulation import new_id


class AgenticWorkflow(Base):
    __tablename__ = "agentic_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True)
    canary_stage_id: Mapped[str] = mapped_column(ForeignKey("simulation_stages.id", ondelete="RESTRICT"), nullable=False)
    current_agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    workflow_status: Mapped[str] = mapped_column(String(40), nullable=False, default="QUEUED")
    failed_vehicle_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    successful_vehicle_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    normalized_errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeline: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    correlations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    hypotheses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence_components: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    global_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approval_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_REQUESTED")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    agent_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"
    __table_args__ = (UniqueConstraint("workflow_id", "sequence", name="uq_workflow_history_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    agent: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    input_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (UniqueConstraint("workflow_id", "agent_type", "attempt", name="uq_agent_execution_attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    authorized_context: Mapped[dict] = mapped_column(JSON, nullable=False)
    tools_allowed: Mapped[list] = mapped_column(JSON, nullable=False)
    tools_used: Mapped[list] = mapped_column(JSON, nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    working_memory: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    incoming_message_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    outgoing_message_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    validations: Mapped[list] = mapped_column(JSON, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_condition: Mapped[str] = mapped_column(String(500), nullable=False)
    failure_condition: Mapped[str] = mapped_column(String(500), nullable=False)
    stop_condition: Mapped[str] = mapped_column(String(500), nullable=False)
    proposed_next_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_source: Mapped[str] = mapped_column(String(40), nullable=False, default="DETERMINISTIC")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (UniqueConstraint("workflow_id", "sequence_number", name="uq_agent_message_sequence"), UniqueConstraint("correlation_id", "sender_agent", "message_type", name="uq_agent_message_idempotency"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True)
    sender_agent: Mapped[str] = mapped_column(String(40), nullable=False)
    receiver_agent: Mapped[str] = mapped_column(String(40), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (UniqueConstraint("agent_execution_id", "sequence_number", name="uq_tool_execution_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_execution_id: Mapped[str] = mapped_column(ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class HumanApprovalRequest(Base):
    __tablename__ = "human_approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class IncidentExplanation(Base):
    __tablename__ = "incident_explanations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    output: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class LLMCallAudit(Base):
    __tablename__ = "llm_call_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    explanation_id: Mapped[str] = mapped_column(ForeignKey("incident_explanations.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class IncidentReport(Base):
    __tablename__ = "incident_reports"
    __table_args__ = (UniqueConstraint("incident_id", "version", name="uq_incident_report_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="RESTRICT"), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True)
    explanation_id: Mapped[str] = mapped_column(ForeignKey("incident_explanations.id", ondelete="RESTRICT"), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    pdf_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    html_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
