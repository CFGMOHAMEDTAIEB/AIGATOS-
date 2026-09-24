from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LiveCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=120)
    component: str = Field(min_length=2, max_length=100)
    current_version: str = Field(min_length=1, max_length=40)
    target_version: str = Field(min_length=1, max_length=40)
    package_type: str = Field(min_length=2, max_length=40)
    package_size_mb: int = Field(ge=1, le=20_000)
    canary_strategy: str = Field(min_length=2, max_length=80)
    failure_threshold: float = Field(gt=0, le=1)


class LiveFleetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_count: int = Field(ge=10, le=100)
    model: str = Field(min_length=2, max_length=100)
    region: str = Field(min_length=2, max_length=80)
    hw_rev_a: int = Field(ge=0, le=100)
    hw_rev_b: int = Field(ge=0, le=100)
    average_battery: int = Field(ge=0, le=100)
    average_network_quality: int = Field(ge=0, le=100)
    available_storage_mb: int = Field(ge=0, le=1_000_000)
    temperature_c: float = Field(ge=-50, le=150)

    @model_validator(mode="after")
    def validate_distribution(self):
        if self.hw_rev_a + self.hw_rev_b != self.vehicle_count:
            raise ValueError("HW_REV_A + HW_REV_B must equal vehicle_count")
        return self


class LiveInjectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal[
        "nominal", "battery_insufficient", "network_unstable", "storage_insufficient",
        "package_corrupted", "hardware_software_incompatible", "ecu_unresponsive",
        "failure_with_rollback",
    ]
    affected_count: int | None = Field(default=None, ge=0, le=100)
    affected_percentage: float | None = Field(default=None, ge=0, le=1)
    target_hardware_revision: Literal["ANY", "HW_REV_A", "HW_REV_B"] = "ANY"
    error_code: str | None = Field(default=None, max_length=80)
    installation_step: str | None = Field(default=None, max_length=80)
    failure_probability: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_affected(self):
        if self.scenario != "nominal" and self.affected_count is None and self.affected_percentage is None:
            raise ValueError("affected_count or affected_percentage is required")
        if self.affected_count is not None and self.affected_percentage is not None:
            raise ValueError("Use affected_count or affected_percentage, not both")
        return self


class LiveSimulationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    created_by: str = Field(min_length=3, max_length=100)
    seed: int = Field(ge=0, le=2_147_483_647)
    campaign: LiveCampaignConfig
    fleet: LiveFleetConfig
    injections: list[LiveInjectionConfig] = Field(default_factory=list, max_length=20)
    simulation_only_confirmed: Literal[True]


class LiveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    user: str = Field(min_length=3, max_length=100)
    comment: str = Field(min_length=5, max_length=1000)
    timestamp: datetime
    simulation_only_confirmed: Literal[True]
