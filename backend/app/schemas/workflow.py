from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgenticIncidentState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_id: str
    incident_id: str
    campaign_id: str
    canary_stage_id: str
    current_agent: str | None
    workflow_status: str
    failed_vehicle_ids: list[str]
    successful_vehicle_ids: list[str]
    normalized_errors: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    correlations: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    evidence_ids: list[str]
    confidence_components: dict[str, Any]
    global_confidence: float | None
    recommended_actions: list[dict[str, Any]]
    approval_status: str
    retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class HumanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: str = Field(min_length=3, max_length=100)
    timestamp: datetime
    comment: str = Field(min_length=5, max_length=1000)
