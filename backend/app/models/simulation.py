from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.entities import utc_now


def new_id() -> str:
    return str(uuid4())


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    hw_b_failure_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    failure_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    current_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SimulationStage(Base):
    __tablename__ = "simulation_stages"
    __table_args__ = (UniqueConstraint("simulation_id", "stage_number", name="uq_simulation_stage"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluation_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evaluated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class SimulationVehicle(Base):
    __tablename__ = "simulation_vehicles"
    __table_args__ = (
        UniqueConstraint("simulation_id", "vehicle_index", name="uq_simulation_vehicle_index"),
        UniqueConstraint("simulation_id", "vehicle_id", name="uq_simulation_vehicle_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False)
    ecu_id: Mapped[str] = mapped_column(ForeignKey("ecus.id", ondelete="RESTRICT"), nullable=False)
    vehicle_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rolled_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OTAEvent(Base):
    __tablename__ = "ota_events"
    __table_args__ = (UniqueConstraint("simulation_id", "vehicle_id", "sequence", name="uq_event_sequence"),)

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True)
    ecu_id: Mapped[str] = mapped_column(ForeignKey("ecus.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    installation_step: Mapped[str] = mapped_column(String(40), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    software_version: Mapped[str] = mapped_column(String(100), nullable=False)
    hardware_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    battery_level: Mapped[int] = mapped_column(Integer, nullable=False)
    network_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    free_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    details: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("simulation_id", "stage_number", name="uq_incident_simulation_stage"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False)
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="high")
    failure_rate: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    details: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"
    __table_args__ = (UniqueConstraint("incident_id", "event_id", name="uq_incident_evidence_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("ota_events.event_id", ondelete="RESTRICT"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False, default="FAILED_VEHICLE_TIMELINE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
