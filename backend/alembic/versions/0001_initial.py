"""Initial vehicle, ECU, package and campaign tables.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vin", sa.String(17), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("hardware_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("vin"),
    )
    op.create_index("ix_vehicles_vin", "vehicles", ["vin"], unique=True)
    op.create_table(
        "software_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("target_hardware", sa.String(100), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_package_name_version"),
    )
    op.create_table(
        "ecus",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hardware_version", sa.String(100), nullable=False),
        sa.Column("software_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("vehicle_id", "name", name="uq_ecu_vehicle_name"),
    )
    op.create_index("ix_ecus_vehicle_id", "ecus", ["vehicle_id"])
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("software_package_id", sa.String(36), sa.ForeignKey("software_packages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("canary_percentage", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_software_package_id", "campaigns", ["software_package_id"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_software_package_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("ix_ecus_vehicle_id", table_name="ecus")
    op.drop_table("ecus")
    op.drop_table("software_packages")
    op.drop_index("ix_vehicles_vin", table_name="vehicles")
    op.drop_table("vehicles")
