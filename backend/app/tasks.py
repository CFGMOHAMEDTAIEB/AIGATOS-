from app.celery_app import celery_app
from app.db import SessionLocal
from app.services.ota_simulator import run_stage
from app.services.agentic_workflow import run_workflow


@celery_app.task(name="aigatos.simulate_stage")
def simulate_stage(simulation_id: str, stage_number: int) -> None:
    with SessionLocal() as db:
        run_stage(db, simulation_id, stage_number)


@celery_app.task(name="aigatos.run_investigation", soft_time_limit=310, time_limit=330)
def run_investigation(workflow_id: str) -> None:
    with SessionLocal() as db:
        run_workflow(db, workflow_id)
