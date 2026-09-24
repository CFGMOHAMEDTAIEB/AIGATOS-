from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.crud import crud_router
from app.api.simulations import router as simulations_router
from app.api.workflows import router as workflows_router
from app.api.explanations import router as explanations_router
from app.api.reports import router as reports_router
from app.api.frontend import router as frontend_router
from app.api.live import router as live_router
from app.api.llm import router as llm_router
from app.llm_config import load_llm_settings, log_llm_settings
from app.operation_mode import get_operation_mode
from app.models import Campaign, ECU, SoftwarePackage, Vehicle
from app.schemas.entities import (
    CampaignCreate, CampaignRead, CampaignUpdate,
    ECUCreate, ECURead, ECUUpdate,
    SoftwarePackageCreate, SoftwarePackageRead, SoftwarePackageUpdate,
    VehicleCreate, VehicleRead, VehicleUpdate,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    log_llm_settings(load_llm_settings())
    get_operation_mode()
    yield


app = FastAPI(title="AIGATOS API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Idempotency-Key"],
)


@app.get("/api/v1/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(crud_router("/api/v1/vehicles", "vehicles", Vehicle, VehicleCreate, VehicleUpdate, VehicleRead))
app.include_router(crud_router("/api/v1/ecus", "ecus", ECU, ECUCreate, ECUUpdate, ECURead, {"vehicle_id": Vehicle}))
app.include_router(crud_router("/api/v1/software-packages", "software-packages", SoftwarePackage, SoftwarePackageCreate, SoftwarePackageUpdate, SoftwarePackageRead))
app.include_router(crud_router("/api/v1/campaigns", "campaigns", Campaign, CampaignCreate, CampaignUpdate, CampaignRead, {"software_package_id": SoftwarePackage}))

app.include_router(simulations_router)
app.include_router(workflows_router)
app.include_router(explanations_router)
app.include_router(reports_router)
app.include_router(frontend_router)
app.include_router(live_router)
app.include_router(llm_router)
