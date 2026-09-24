"""phase 4b incident reports

Revision ID: f026a51d9b32
Revises: e915f40c8a21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f026a51d9b32"
down_revision: Union[str, Sequence[str], None] = "e915f40c8a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incident_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("explanation_id", sa.String(length=36), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template_version", sa.String(length=50), nullable=False),
        sa.Column("pdf_path", sa.String(length=1000), nullable=False),
        sa.Column("html_path", sa.String(length=1000), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["explanation_id"], ["incident_explanations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "version", name="uq_incident_report_version"),
    )
    op.create_index(op.f("ix_incident_reports_explanation_id"), "incident_reports", ["explanation_id"], unique=False)
    op.create_index(op.f("ix_incident_reports_incident_id"), "incident_reports", ["incident_id"], unique=False)
    op.create_index(op.f("ix_incident_reports_input_hash"), "incident_reports", ["input_hash"], unique=True)
    op.create_index(op.f("ix_incident_reports_workflow_id"), "incident_reports", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_incident_reports_workflow_id"), table_name="incident_reports")
    op.drop_index(op.f("ix_incident_reports_input_hash"), table_name="incident_reports")
    op.drop_index(op.f("ix_incident_reports_incident_id"), table_name="incident_reports")
    op.drop_index(op.f("ix_incident_reports_explanation_id"), table_name="incident_reports")
    op.drop_table("incident_reports")
