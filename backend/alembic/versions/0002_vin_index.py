"""Remove duplicate VIN unique constraint.

Revision ID: 0002_vin_index
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_vin_index"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("vehicles_vin_key", "vehicles", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("vehicles_vin_key", "vehicles", ["vin"])
