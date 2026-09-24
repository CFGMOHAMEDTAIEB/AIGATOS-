from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Scenario = Literal["nominal", "battery_insufficient", "network_unstable", "storage_insufficient", "package_corrupted", "hardware_software_incompatible", "ecu_unresponsive", "failure_with_rollback"]
HardwareRevision = Literal["ANY", "HW_REV_A", "HW_REV_B"]
SCENARIO_RULES: dict[str, tuple[str | None, str]] = {
    "nominal": (None, "SUCCESS"),
    "battery_insufficient": ("BATTERY_INSUFFICIENT", "ELIGIBILITY_CHECK"),
    "network_unstable": ("NETWORK_UNSTABLE", "DOWNLOADING"),
    "storage_insufficient": ("STORAGE_INSUFFICIENT", "ELIGIBILITY_CHECK"),
    "package_corrupted": ("PACKAGE_CORRUPTED", "VERIFYING_PACKAGE"),
    "hardware_software_incompatible": ("MEMORY_LAYOUT_MISMATCH", "MEMORY_VALIDATION"),
    "ecu_unresponsive": ("ECU_NOT_RESPONDING", "REBOOTING"),
    "failure_with_rollback": ("INSTALLATION_FAILED", "INSTALLING"),
}
PACKAGE_TYPES = {"DELTA", "FULL"}
CANARY_STRATEGIES = {"CONTROLLED", "CONTROLLED_30", "PROGRESSIVE", "FIXED_COHORT"}


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

    @model_validator(mode="after")
    def validate_allowlists(self):
        self.package_type = self.package_type.upper()
        self.canary_strategy = self.canary_strategy.upper()
        if self.package_type not in PACKAGE_TYPES:
            raise ValueError(f"package_type must be one of {sorted(PACKAGE_TYPES)}")
        if self.canary_strategy not in CANARY_STRATEGIES:
            raise ValueError(f"canary_strategy must be one of {sorted(CANARY_STRATEGIES)}")
        return self


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
    scenario: Scenario
    affected_count: int | None = Field(default=None, ge=0, le=100)
    affected_percentage: float | None = Field(default=None, ge=0, le=1)
    target_hardware_revision: HardwareRevision = "ANY"
    error_code: str | None = Field(default=None, max_length=80)
    installation_step: str | None = Field(default=None, max_length=80)
    failure_probability: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_rule(self):
        if (self.affected_count is None) == (self.affected_percentage is None):
            raise ValueError("Use exactly one of affected_count or affected_percentage")
        allowed_error, allowed_step = SCENARIO_RULES[self.scenario]
        normalized_error = self.error_code.upper() if self.error_code else None
        normalized_step = self.installation_step.upper() if self.installation_step else None
        if self.scenario == "nominal":
            if self.failure_probability != 0:
                raise ValueError("nominal failure_probability must be 0")
            if normalized_error is not None or normalized_step != allowed_step:
                raise ValueError("nominal must use no error_code and installation_step SUCCESS")
        elif normalized_error != allowed_error or normalized_step != allowed_step:
            raise ValueError(f"{self.scenario} requires error_code={allowed_error} and installation_step={allowed_step}")
        self.error_code = normalized_error
        self.installation_step = normalized_step
        return self


class LiveSimulationDraft(BaseModel):
    """Validated configuration shared by manual entry and the LLM draft endpoint."""
    model_config = ConfigDict(extra="forbid")
    created_by: str = Field(default="ota-operator", min_length=3, max_length=100)
    seed: int = Field(default=20260923, ge=0, le=2_147_483_647)
    campaign: LiveCampaignConfig
    fleet: LiveFleetConfig
    injections: list[LiveInjectionConfig] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_capacity(self):
        total_requested = 0
        hardware_requested = {"HW_REV_A": 0, "HW_REV_B": 0}
        for rule in self.injections:
            requested = rule.affected_count
            if requested is None:
                requested = int(self.fleet.vehicle_count * (rule.affected_percentage or 0) + 0.999999)
            if requested > self.fleet.vehicle_count:
                raise ValueError("affected_count must be <= vehicle_count")
            total_requested += requested
            if rule.target_hardware_revision != "ANY":
                hardware_requested[rule.target_hardware_revision] += requested
        if total_requested > self.fleet.vehicle_count:
            raise ValueError("sum of targeted vehicles must be <= vehicle_count")
        if hardware_requested["HW_REV_A"] > self.fleet.hw_rev_a:
            raise ValueError("HW_REV_A targeted vehicles exceed the available fleet")
        if hardware_requested["HW_REV_B"] > self.fleet.hw_rev_b:
            raise ValueError("HW_REV_B targeted vehicles exceed the available fleet")
        return self


class LiveSimulationCreate(LiveSimulationDraft):
    simulation_only_confirmed: Literal[True]


class ConfigurationDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=4000)


class LiveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    user: str = Field(min_length=3, max_length=100)
    comment: str = Field(min_length=5, max_length=1000)
    timestamp: datetime
    simulation_only_confirmed: Literal[True]
