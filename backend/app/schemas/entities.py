from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VehicleFields(StrictSchema):
    vin: str = Field(min_length=17, max_length=17)
    model: str = Field(min_length=1, max_length=100)
    hardware_version: str = Field(min_length=1, max_length=100)


class VehicleCreate(VehicleFields):
    pass


class VehicleUpdate(StrictSchema):
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    hardware_version: str | None = Field(default=None, min_length=1, max_length=100)


class VehicleRead(VehicleFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class ECUFields(StrictSchema):
    vehicle_id: str
    name: str = Field(min_length=1, max_length=100)
    hardware_version: str = Field(min_length=1, max_length=100)
    software_version: str = Field(min_length=1, max_length=100)


class ECUCreate(ECUFields):
    pass


class ECUUpdate(StrictSchema):
    vehicle_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    hardware_version: str | None = Field(default=None, min_length=1, max_length=100)
    software_version: str | None = Field(default=None, min_length=1, max_length=100)


class ECURead(ECUFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class SoftwarePackageFields(StrictSchema):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    target_hardware: str = Field(min_length=1, max_length=100)
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class SoftwarePackageCreate(SoftwarePackageFields):
    pass


class SoftwarePackageUpdate(StrictSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    version: str | None = Field(default=None, min_length=1, max_length=100)
    target_hardware: str | None = Field(default=None, min_length=1, max_length=100)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


class SoftwarePackageRead(SoftwarePackageFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class CampaignFields(StrictSchema):
    name: str = Field(min_length=1, max_length=150)
    software_package_id: str
    status: Literal["draft"] = "draft"
    canary_percentage: int = Field(default=5, ge=1, le=100)


class CampaignCreate(CampaignFields):
    pass


class CampaignUpdate(StrictSchema):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    software_package_id: str | None = None
    canary_percentage: int | None = Field(default=None, ge=1, le=100)


class CampaignRead(CampaignFields):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
