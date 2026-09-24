from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentType = Literal["MONITORING", "LOG_ANALYSIS", "CORRELATION", "RCA", "DECISION", "HUMAN", "ORCHESTRATOR"]
MessageType = Literal[
    "INCIDENT_DETECTED",
    "LOG_SUMMARY_READY",
    "CORRELATION_READY",
    "RCA_READY",
    "RECOMMENDATION_PROPOSED",
    "HUMAN_APPROVAL_REQUIRED",
    "VALIDATION_FAILED",
]


REQUIRED_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "INCIDENT_DETECTED": frozenset({"failed_vehicle_count", "successful_vehicle_count"}),
    "LOG_SUMMARY_READY": frozenset({"normalized_error_count", "timeline_count"}),
    "CORRELATION_READY": frozenset({"correlation_count"}),
    "RCA_READY": frozenset({"hypothesis_count", "global_confidence"}),
    "RECOMMENDATION_PROPOSED": frozenset({"recommended_action_count"}),
    "HUMAN_APPROVAL_REQUIRED": frozenset({"recommended_action_count", "approval_status"}),
    "VALIDATION_FAILED": frozenset({"error_code"}),
}


class AgentMessageContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_agent: AgentType
    receiver_agent: AgentType
    message_type: MessageType
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    correlation_id: str = Field(min_length=1, max_length=36)

    @model_validator(mode="after")
    def validate_payload_contract(self) -> "AgentMessageContract":
        missing = REQUIRED_PAYLOAD_FIELDS[self.message_type] - self.payload.keys()
        if missing:
            raise ValueError(f"Missing payload fields for {self.message_type}: {sorted(missing)}")
        if self.message_type != "VALIDATION_FAILED" and not self.evidence_ids:
            raise ValueError("Successful agent messages require evidence_ids")
        return self


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_type: AgentType
    tool_name: str = Field(min_length=1, max_length=100)
    input_payload: dict[str, Any] = Field(default_factory=dict)


class ToolInputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_status: str | None = None
    failed_vehicle_count: int = Field(default=0, ge=0)
    successful_vehicle_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    correlation_count: int = Field(default=0, ge=0)
    hypothesis_count: int = Field(default=0, ge=0)


class ToolOutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed_vehicle_count: int = Field(default=0, ge=0)
    successful_vehicle_count: int = Field(default=0, ge=0)
    normalized_error_count: int = Field(default=0, ge=0)
    timeline_count: int = Field(default=0, ge=0)
    correlation_count: int = Field(default=0, ge=0)
    hypothesis_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    recommended_action_count: int = Field(default=0, ge=0)
    global_confidence: float | None = Field(default=None, ge=0, le=1)
    approval_status: str
