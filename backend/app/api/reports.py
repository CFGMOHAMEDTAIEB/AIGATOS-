from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IncidentReport
from app.services.incident_report import DEFAULT_OUTPUT_DIR, ReportValidationError, generate_report


router = APIRouter(tags=["incident-reports"])


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: str
    explanation_id: str


def _report_response(report: IncidentReport, cached: bool) -> dict:
    return {
        "report_id": report.id, "incident_id": report.incident_id,
        "workflow_id": report.workflow_id, "explanation_id": report.explanation_id,
        "version": report.version, "template_version": report.template_version,
        "pdf_path": report.pdf_path, "html_path": report.html_path,
        "pdf_sha256": report.pdf_sha256, "generated_at": report.generated_at,
        "cached": cached,
    }


@router.post("/incidents/{incident_id}/reports")
def create_report(incident_id: str, payload: ReportRequest, db: Session = Depends(get_db)) -> dict:
    try:
        report, cached = generate_report(db, payload.workflow_id, incident_id, payload.explanation_id)
    except ReportValidationError as error:
        status = 404 if "not found" in str(error).lower() else 409
        raise HTTPException(status_code=status, detail=str(error)) from error
    return _report_response(report, cached)


@router.get("/reports/{report_id}/pdf")
def download_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(IncidentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    path = Path(report.pdf_path).resolve()
    root = DEFAULT_OUTPUT_DIR.resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=409, detail="Archived PDF is unavailable")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
