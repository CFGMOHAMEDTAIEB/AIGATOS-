"""live simulation sessions

Revision ID: aa50c6e5d1b4
Revises: f026a51d9b32
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa50c6e5d1b4"
down_revision: Union[str, Sequence[str], None] = "f026a51d9b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "live_simulation_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("environment", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("simulation_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=True),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("creation_key", sa.String(length=100), nullable=False),
        sa.Column("start_key", sa.String(length=100), nullable=True),
        sa.Column("investigation_key", sa.String(length=100), nullable=True),
        sa.Column("decision_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["simulation_id"], ["simulation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_id"], ["agentic_workflows.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id"), sa.UniqueConstraint("simulation_id"),
        sa.UniqueConstraint("incident_id"), sa.UniqueConstraint("workflow_id"),
        sa.UniqueConstraint("creation_key"), sa.UniqueConstraint("start_key"),
        sa.UniqueConstraint("investigation_key"), sa.UniqueConstraint("decision_key"),
    )


def downgrade() -> None:
    op.drop_table("live_simulation_sessions")
