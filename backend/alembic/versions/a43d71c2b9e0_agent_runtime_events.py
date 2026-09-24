"""Add observable agent runtime state and resumable workflow events.

Revision ID: a43d71c2b9e0
Revises: 7c91a45e2f10
"""
from alembic import op
import sqlalchemy as sa


revision = "a43d71c2b9e0"
down_revision = "7c91a45e2f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_executions", sa.Column("current_state", sa.String(30), nullable=False, server_default="OBSERVE"))
    op.add_column("agent_executions", sa.Column("observation", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agent_executions", sa.Column("plan", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agent_executions", sa.Column("selected_tool", sa.String(100), nullable=True))
    op.add_column("agent_executions", sa.Column("tool_call_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("agent_executions", sa.Column("validation_result", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agent_executions", sa.Column("runtime_retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_executions", sa.Column("stop_reason", sa.String(500), nullable=True))
    op.add_column("agent_messages", sa.Column("summary", sa.String(500), nullable=False, server_default=""))
    op.add_column("agent_messages", sa.Column("tool_call_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("agentic_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_id", "sequence_number", name="uq_agent_event_sequence"),
    )
    op.create_index("ix_agent_events_workflow_id", "agent_events", ["workflow_id"])
    op.create_index("ix_agent_events_incident_id", "agent_events", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_events_incident_id", table_name="agent_events")
    op.drop_index("ix_agent_events_workflow_id", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_column("agent_messages", "tool_call_ids")
    op.drop_column("agent_messages", "summary")
    op.drop_column("agent_executions", "stop_reason")
    op.drop_column("agent_executions", "runtime_retry_count")
    op.drop_column("agent_executions", "validation_result")
    op.drop_column("agent_executions", "tool_call_ids")
    op.drop_column("agent_executions", "selected_tool")
    op.drop_column("agent_executions", "plan")
    op.drop_column("agent_executions", "observation")
    op.drop_column("agent_executions", "current_state")
