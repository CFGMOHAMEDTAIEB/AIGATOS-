"""phase 4a explanations

Revision ID: e915f40c8a21
Revises: c824a47b1d32
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e915f40c8a21"
down_revision: Union[str, Sequence[str], None] = "c824a47b1d32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incident_explanations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_explanations_incident_id"), "incident_explanations", ["incident_id"], unique=False)
    op.create_index(op.f("ix_incident_explanations_input_hash"), "incident_explanations", ["input_hash"], unique=True)
    op.create_index(op.f("ix_incident_explanations_workflow_id"), "incident_explanations", ["workflow_id"], unique=False)
    op.create_table(
        "llm_call_audit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("explanation_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["explanation_id"], ["incident_explanations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_call_audit_explanation_id"), "llm_call_audit", ["explanation_id"], unique=False)
    op.create_index(op.f("ix_llm_call_audit_incident_id"), "llm_call_audit", ["incident_id"], unique=False)
    op.create_index(op.f("ix_llm_call_audit_input_hash"), "llm_call_audit", ["input_hash"], unique=False)
    op.create_index(op.f("ix_llm_call_audit_workflow_id"), "llm_call_audit", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_call_audit_workflow_id"), table_name="llm_call_audit")
    op.drop_index(op.f("ix_llm_call_audit_input_hash"), table_name="llm_call_audit")
    op.drop_index(op.f("ix_llm_call_audit_incident_id"), table_name="llm_call_audit")
    op.drop_index(op.f("ix_llm_call_audit_explanation_id"), table_name="llm_call_audit")
    op.drop_table("llm_call_audit")
    op.drop_index(op.f("ix_incident_explanations_workflow_id"), table_name="incident_explanations")
    op.drop_index(op.f("ix_incident_explanations_input_hash"), table_name="incident_explanations")
    op.drop_index(op.f("ix_incident_explanations_incident_id"), table_name="incident_explanations")
    op.drop_table("incident_explanations")
