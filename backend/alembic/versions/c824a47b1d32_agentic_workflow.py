"""agentic workflow

Revision ID: c824a47b1d32
Revises: b713f36a9c21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c824a47b1d32"
down_revision: Union[str, Sequence[str], None] = "b713f36a9c21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agentic_workflows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("canary_stage_id", sa.String(length=36), nullable=False),
        sa.Column("current_agent", sa.String(length=40), nullable=True),
        sa.Column("workflow_status", sa.String(length=40), nullable=False),
        sa.Column("failed_vehicle_ids", sa.JSON(), nullable=False),
        sa.Column("successful_vehicle_ids", sa.JSON(), nullable=False),
        sa.Column("normalized_errors", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("correlations", sa.JSON(), nullable=False),
        sa.Column("hypotheses", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence_components", sa.JSON(), nullable=False),
        sa.Column("global_confidence", sa.Float(), nullable=True),
        sa.Column("recommended_actions", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("agent_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canary_stage_id"], ["simulation_stages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agentic_workflows_campaign_id"), "agentic_workflows", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_agentic_workflows_incident_id"), "agentic_workflows", ["incident_id"], unique=True)
    op.create_table(
        "human_approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_human_approval_requests_workflow_id"), "human_approval_requests", ["workflow_id"], unique=True)
    op.create_table(
        "workflow_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("input_summary", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "sequence", name="uq_workflow_history_sequence"),
    )
    op.create_index(op.f("ix_workflow_history_workflow_id"), "workflow_history", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_history_workflow_id"), table_name="workflow_history")
    op.drop_table("workflow_history")
    op.drop_index(op.f("ix_human_approval_requests_workflow_id"), table_name="human_approval_requests")
    op.drop_table("human_approval_requests")
    op.drop_index(op.f("ix_agentic_workflows_incident_id"), table_name="agentic_workflows")
    op.drop_index(op.f("ix_agentic_workflows_campaign_id"), table_name="agentic_workflows")
    op.drop_table("agentic_workflows")
