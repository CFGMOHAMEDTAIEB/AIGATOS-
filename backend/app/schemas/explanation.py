from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    statement: str = Field(min_length=3, max_length=1000)


class ExplanationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_summary: str = Field(min_length=10, max_length=4000)
    probable_root_cause: str = Field(min_length=10, max_length=3000)
    confidence_interpretation: str = Field(min_length=10, max_length=2000)
    evidence_citations: list[EvidenceCitation] = Field(min_length=1, max_length=50)
    alternative_hypotheses: list[str] = Field(max_length=20)
    recommended_next_steps: list[str] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=20)
    generated_at: datetime
    model_name: str
    prompt_version: str
