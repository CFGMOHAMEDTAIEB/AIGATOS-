"""monitoring incident evidence

Revision ID: b713f36a9c21
Revises: 315c63330444
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b713f36a9c21"
down_revision: Union[str, Sequence[str], None] = "315c63330444"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("anomaly_score", sa.Float(), nullable=True))
    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["ota_events.event_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "event_id", name="uq_incident_evidence_event"),
    )
    op.create_index(op.f("ix_incident_evidence_event_id"), "incident_evidence", ["event_id"], unique=False)
    op.create_index(op.f("ix_incident_evidence_incident_id"), "incident_evidence", ["incident_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_incident_evidence_incident_id"), table_name="incident_evidence")
    op.drop_index(op.f("ix_incident_evidence_event_id"), table_name="incident_evidence")
    op.drop_table("incident_evidence")
    op.drop_column("incidents", "anomaly_score")
