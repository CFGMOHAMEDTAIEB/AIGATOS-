"""persistent agent contracts, messages and tool executions

Revision ID: 7c91a45e2f10
Revises: aa50c6e5d1b4
"""
from alembic import op
import sqlalchemy as sa

revision = "7c91a45e2f10"
down_revision = "aa50c6e5d1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("agent_executions",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("workflow_id",sa.String(36),sa.ForeignKey("agentic_workflows.id",ondelete="CASCADE"),nullable=False),
        sa.Column("incident_id",sa.String(36),sa.ForeignKey("incidents.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("agent_type",sa.String(40),nullable=False),sa.Column("objective",sa.String(500),nullable=False),sa.Column("status",sa.String(30),nullable=False),
        sa.Column("authorized_context",sa.JSON(),nullable=False),sa.Column("tools_allowed",sa.JSON(),nullable=False),sa.Column("tools_used",sa.JSON(),nullable=False),
        sa.Column("input_payload",sa.JSON(),nullable=False),sa.Column("output_payload",sa.JSON(),nullable=False),sa.Column("working_memory",sa.JSON(),nullable=False),
        sa.Column("evidence_ids",sa.JSON(),nullable=False),sa.Column("incoming_message_ids",sa.JSON(),nullable=False),sa.Column("outgoing_message_ids",sa.JSON(),nullable=False),sa.Column("validations",sa.JSON(),nullable=False),sa.Column("attempt",sa.Integer(),nullable=False),sa.Column("duration_ms",sa.Integer(),nullable=False),
        sa.Column("success_condition",sa.String(500),nullable=False),sa.Column("failure_condition",sa.String(500),nullable=False),sa.Column("stop_condition",sa.String(500),nullable=False),
        sa.Column("proposed_next_state",sa.String(40)),sa.Column("llm_provider",sa.String(40)),sa.Column("llm_model",sa.String(200)),sa.Column("output_source",sa.String(40),nullable=False),sa.Column("error_code",sa.String(100)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workflow_id","agent_type","attempt",name="uq_agent_execution_attempt"))
    op.create_index("ix_agent_executions_workflow_id","agent_executions",["workflow_id"]);op.create_index("ix_agent_executions_incident_id","agent_executions",["incident_id"])
    op.create_table("agent_messages",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("workflow_id",sa.String(36),sa.ForeignKey("agentic_workflows.id",ondelete="CASCADE"),nullable=False),sa.Column("incident_id",sa.String(36),sa.ForeignKey("incidents.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("sender_agent",sa.String(40),nullable=False),sa.Column("receiver_agent",sa.String(40),nullable=False),sa.Column("message_type",sa.String(50),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("evidence_ids",sa.JSON(),nullable=False),
        sa.Column("correlation_id",sa.String(36),nullable=False),sa.Column("sequence_number",sa.Integer(),nullable=False),sa.Column("validation_status",sa.String(30),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("consumed_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workflow_id","sequence_number",name="uq_agent_message_sequence"),sa.UniqueConstraint("correlation_id","sender_agent","message_type",name="uq_agent_message_idempotency"))
    op.create_index("ix_agent_messages_workflow_id","agent_messages",["workflow_id"]);op.create_index("ix_agent_messages_incident_id","agent_messages",["incident_id"]);op.create_index("ix_agent_messages_correlation_id","agent_messages",["correlation_id"])
    op.create_table("tool_executions",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("agent_execution_id",sa.String(36),sa.ForeignKey("agent_executions.id",ondelete="CASCADE"),nullable=False),sa.Column("workflow_id",sa.String(36),sa.ForeignKey("agentic_workflows.id",ondelete="CASCADE"),nullable=False),
        sa.Column("agent_type",sa.String(40),nullable=False),sa.Column("tool_name",sa.String(100),nullable=False),sa.Column("mode",sa.String(20),nullable=False),sa.Column("input_payload",sa.JSON(),nullable=False),sa.Column("output_payload",sa.JSON(),nullable=False),sa.Column("status",sa.String(30),nullable=False),sa.Column("duration_ms",sa.Integer(),nullable=False),sa.Column("sequence_number",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("agent_execution_id","sequence_number",name="uq_tool_execution_sequence"))
    op.create_index("ix_tool_executions_agent_execution_id","tool_executions",["agent_execution_id"]);op.create_index("ix_tool_executions_workflow_id","tool_executions",["workflow_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_executions_workflow_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_agent_execution_id", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index("ix_agent_messages_correlation_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_incident_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_workflow_id", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_executions_incident_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_workflow_id", table_name="agent_executions")
    op.drop_table("agent_executions")
