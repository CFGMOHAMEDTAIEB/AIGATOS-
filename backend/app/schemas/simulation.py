from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SimulationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    hw_b_failure_probability: float = Field(default=0.9, ge=0, le=1)
    failure_threshold: float = Field(default=0.2, ge=0, le=1)


class StageEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    note: str = Field(min_length=5, max_length=1000)
    reviewer: str = Field(min_length=3, max_length=100)


class OTAEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    timestamp: datetime
    campaign_id: str
    vehicle_id: str
    ecu_id: str
    event_type: str
    installation_step: str
    error_code: str | None
    software_version: str
    hardware_revision: str
    battery_level: int = Field(ge=0, le=100)
    network_quality: int = Field(ge=0, le=100)
    free_storage_mb: int = Field(ge=0)
    attempt_number: int = Field(ge=1)
    metadata: dict[str, Any]
    sequence: int = Field(ge=1)
    stage_number: int = Field(ge=1, le=3)
    simulation_id: str

    @field_validator("timestamp")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("timestamp must be timezone-aware UTC")
        return value
