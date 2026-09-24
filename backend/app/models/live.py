from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.entities import utc_now
from app.models.simulation import new_id


class LiveSimulationSession(Base):
    __tablename__ = "live_simulation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="LIVE_SIMULATION")
    environment: Mapped[str] = mapped_column(String(30), nullable=False, default="SIMULATED")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PREPARING")
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), unique=True, nullable=False)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), unique=True, nullable=False)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"), unique=True, nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("agentic_workflows.id", ondelete="RESTRICT"), unique=True, nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    creation_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    start_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    investigation_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    decision_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
