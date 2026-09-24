"""Reproducible HTML/PDF archive built only from validated PostgreSQL facts."""

from __future__ import annotations

import hashlib
import html
import json
from io import BytesIO
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from string import Template

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AgenticWorkflow, AuditLog, Campaign, HumanApprovalRequest, Incident,
    IncidentEvidence, IncidentExplanation, IncidentReport, LLMCallAudit,
    OTAEvent, SimulationRun, SimulationStage, WorkflowHistory,
)
from app.services.agentic_workflow import validate_evidence_ids


TEMPLATE_VERSION = "incident-report-v1.1"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "incidents"
HTML_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "incident_report_v1.html"
FORBIDDEN_TEXT = ("authorization:", "bearer ", "api_key=", "api-key=", "nvapi-")


class ReportValidationError(ValueError):
    pass


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _secret_free(value: str) -> None:
    if any(marker in value.lower() for marker in FORBIDDEN_TEXT):
        raise ReportValidationError("Sensitive material detected in report content")


def collect_report_data(db: Session, workflow_id: str, incident_id: str, explanation_id: str) -> dict:
    workflow = db.get(AgenticWorkflow, workflow_id)
    incident = db.get(Incident, incident_id)
    explanation = db.get(IncidentExplanation, explanation_id)
    if workflow is None or incident is None or explanation is None:
        raise ReportValidationError("Workflow, incident, or explanation not found")
    if workflow.incident_id != incident.id or explanation.workflow_id != workflow.id or explanation.incident_id != incident.id:
        raise ReportValidationError("Identifiers do not belong to the same investigation")
    approval = db.scalar(select(HumanApprovalRequest).where(HumanApprovalRequest.workflow_id == workflow.id))
    if workflow.workflow_status != "WAITING_FOR_HUMAN_APPROVAL" or workflow.approval_status != "PENDING":
        raise ReportValidationError("Workflow is not waiting for human approval")
    if approval is None or approval.status != "PENDING" or approval.decided_at is not None:
        raise ReportValidationError("Approval request is no longer pending")
    if explanation.source != "DETERMINISTIC_FALLBACK":
        raise ReportValidationError("Explanation source must be DETERMINISTIC_FALLBACK")
    if abs((workflow.global_confidence or 0) - 0.620644) > 1e-12:
        raise ReportValidationError("Deterministic score changed")
    if incident.anomaly_score is not None or any(item.get("executed") for item in workflow.recommended_actions):
        raise ReportValidationError("Phase 4B safety invariant changed")

    run = db.get(SimulationRun, incident.simulation_id)
    campaign = db.get(Campaign, incident.campaign_id)
    stage2 = db.scalar(select(SimulationStage).where(SimulationStage.simulation_id == run.id, SimulationStage.stage_number == 2))
    stage3 = db.scalar(select(SimulationStage).where(SimulationStage.simulation_id == run.id, SimulationStage.stage_number == 3))
    if campaign.status != "draft" or run.current_stage != 2 or stage3.status != "pending" or stage3.task_id is not None:
        raise ReportValidationError("Campaign or Canary 3 changed")

    evidence_ids = [item["evidence_id"] for item in explanation.output["evidence_citations"]]
    validate_evidence_ids(db, incident.id, evidence_ids)
    linked = db.scalar(select(func.count()).select_from(IncidentEvidence).where(IncidentEvidence.incident_id == incident.id))
    failures = db.scalar(select(func.count()).select_from(IncidentEvidence).join(
        OTAEvent, OTAEvent.event_id == IncidentEvidence.event_id,
    ).where(IncidentEvidence.incident_id == incident.id, OTAEvent.event_type == "FAILURE"))
    history = list(db.scalars(select(WorkflowHistory).where(WorkflowHistory.workflow_id == workflow.id).order_by(WorkflowHistory.sequence)))
    audits = list(db.scalars(select(LLMCallAudit).where(LLMCallAudit.explanation_id == explanation.id).order_by(LLMCallAudit.created_at)))
    stage1_audit = db.scalar(select(AuditLog).where(
        AuditLog.simulation_id == run.id, AuditLog.stage_number == 1, AuditLog.decision == "approved",
    ).order_by(AuditLog.timestamp.desc()))
    hw_b = next(item for item in workflow.correlations if item.get("factor") == "hardware_revision" and item.get("level") == "HW_REV_B")
    hw_a = next(item for item in workflow.correlations if item.get("factor") == "hardware_revision" and item.get("level") == "HW_REV_A")
    data = {
        "workflow_id": workflow.id, "incident_id": incident.id, "explanation_id": explanation.id,
        "severity": incident.severity.upper(), "workflow_status": workflow.workflow_status,
        "vehicle_count": stage2.vehicle_count, "success_count": stage2.success_count,
        "failure_count": stage2.failure_count, "rollback_count": stage2.rollback_count,
        "failure_rate": incident.failure_rate, "global_confidence": workflow.global_confidence,
        "incident_summary": explanation.output["incident_summary"],
        "probable_root_cause": explanation.output["probable_root_cause"],
        "normalized_errors": workflow.normalized_errors, "hw_b": hw_b, "hw_a": hw_a,
        "hypothesis": workflow.hypotheses[0],
        "alternative_hypotheses": explanation.output["alternative_hypotheses"],
        "limitations": explanation.output["limitations"], "anomaly_score": incident.anomaly_score,
        "evidence_ids": evidence_ids, "linked_event_count": linked, "failure_event_count": failures,
        "recommendations": workflow.recommended_actions,
        "history": [{"agent": row.agent, "duration_ms": row.duration_ms, "status": row.event_type} for row in history],
        "provider": explanation.provider.upper(), "model": explanation.model_name,
        "explanation_source": explanation.source, "explanation_status": explanation.status,
        "llm_duration_ms": explanation.duration_ms,
        "cache_hit": any(row.status == "CACHE_HIT" for row in audits),
        "stage_one_approved_at": _utc(stage1_audit.timestamp) if stage1_audit else "Enregistrée",
        "incident_detected_at": _utc(incident.created_at),
        "investigation_completed_at": _utc(workflow.updated_at),
    }
    _secret_free(json.dumps(data, ensure_ascii=False, default=str))
    return data


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _html_table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{_e(value)}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{_e(value)}</td>" for value in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(data: dict, generated_at: datetime, version: int) -> str:
    errors = [[x["hardware_revision"], x["error_code"], x["installation_step"], x["count"]] for x in data["normalized_errors"]]
    history = [[x["agent"], x["duration_ms"], x["status"]] for x in data["history"]]
    actions = [[x["action"], x["status"], str(x["executed"]).lower()] for x in data["recommendations"]]
    timeline = [["Canary 1", "Exécutée"], ["Validation humaine", data["stage_one_approved_at"]], ["Canary 2", "30 véhicules - évaluation en attente"], ["Détection incident", data["incident_detected_at"]], ["Investigation multi-agent", data["investigation_completed_at"]], ["Validation humaine", data["workflow_status"]]]
    body = f"""<header><h1>AIGATOS</h1><h2>Rapport d'incident - version {version}</h2><div class="cover-grid">
<div><b>Incident</b><br><code>{_e(data['incident_id'])}</code></div><div><b>Workflow</b><br><code>{_e(data['workflow_id'])}</code></div>
<div><b>Généré en UTC</b><br>{_e(_utc(generated_at))}</div><div><b>Sévérité</b><br>{_e(data['severity'])}</div>
<div><b>Statut</b><br>{_e(data['workflow_status'])}</div><div><b>Source</b><br>{_e(data['explanation_source'])}</div></div></header>
<section><h3>1. Résumé exécutif</h3><div class="metrics"><div class="metric"><strong>{data['vehicle_count']}</strong>véhicules</div><div class="metric"><strong>{data['success_count']}</strong>succès</div><div class="metric"><strong>{data['failure_count']}</strong>échecs</div><div class="metric"><strong>{data['rollback_count']}</strong>rollbacks</div></div><p>Taux d'échec : <b>{data['failure_rate']:.0%}</b>. Score déterministe : <b>{data['global_confidence']:.6f}</b>.</p><p>{_e(data['incident_summary'])}</p><p><b>Cause probable :</b> {_e(data['probable_root_cause'])}</p><p class="notice">Ce rapport ne constitue pas une preuve de causalité confirmée.</p></section>
<section><h3>2. Chronologie Canary</h3>{_html_table(['Étape','État / date UTC'],timeline)}</section>
<section><h3>3. Analyse des erreurs</h3>{_html_table(['Matériel','Erreur','Étape','Véhicules'],errors)}</section>
<section><h3>4. Corrélations</h3>{_html_table(['Cohorte','Échecs','Taux'],[['HW_REV_B','3/3','100 %'],['HW_REV_A','3/27','11,11 %']])}<p>Risk ratio : <b>{data['hw_b']['risk_ratio']:.1f}</b>. IC 95 % : [{data['hw_b']['confidence_interval_95'][0]:.3f}, {data['hw_b']['confidence_interval_95'][1]:.3f}].</p><p class="notice">Corrélation ne signifie pas causalité.</p></section>
<section><h3>5. Root Cause Analysis</h3><p>{_e(data['hypothesis']['statement'])}</p>{_html_table(['Composante','Valeur'],list(map(list,data['hypothesis']['score_components'].items())))}<h4>Hypothèses alternatives</h4><ul>{''.join(f'<li>{_e(x)}</li>' for x in data['alternative_hypotheses'])}</ul><h4>Limitations</h4><ul>{''.join(f'<li>{_e(x)}</li>' for x in data['limitations'])}</ul><p><code>anomaly_score=null</code></p></section>
<section><h3>6. Preuves</h3><p>Événements liés : <b>{data['linked_event_count']}</b>. Événements FAILURE : <b>{data['failure_event_count']}</b>. Aucune preuve inventée.</p><ul>{''.join(f'<li><code>{_e(x)}</code></li>' for x in data['evidence_ids'])}</ul></section>
<section><h3>7. Recommandations consultatives</h3>{_html_table(['Action','Statut','executed'],actions)}</section><section><h3>8. Historique agentique</h3>{_html_table(['Agent','Durée (ms)','Statut'],history)}</section>
<section><h3>9. Gouvernance IA</h3><p>Provider : <b>{_e(data['provider'])}</b>. Modèle : <b>{_e(data['model'])}</b>. Timeout : {data['llm_duration_ms']} ms. Source : <b>{_e(data['explanation_source'])}</b>. Cache hit : {_e(data['cache_hit'])}. Score inchangé. Aucune décision prise par le modèle.</p></section>
<section><h3>10. Validation humaine</h3><p>Décision : ☐ Approve &nbsp;&nbsp; ☐ Reject</p><p>Utilisateur</p><div class="blank"></div><p>Date UTC</p><div class="blank"></div><p>Commentaire</p><div class="blank"></div><div class="blank"></div><p>Aucune signature ou décision n'est préremplie.</p></section><footer>Template {_e(TEMPLATE_VERSION)} - Simulation contrôlée - Aucun déploiement OTA réel</footer>"""
    result = Template(HTML_TEMPLATE.read_text(encoding="utf-8")).substitute(title=_e(f"AIGATOS - Incident {data['incident_id']}"), body=body)
    _secret_free(result)
    return result


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=colors.HexColor("#17324d"), alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontSize=15, leading=19, textColor=colors.HexColor("#157a78"), alignment=TA_CENTER, spaceAfter=24))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=colors.HexColor("#17324d"), spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#157a78"), spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodySmall"], fontName="Helvetica-Bold", textColor=colors.white))
    styles.add(ParagraphStyle(name="Notice", parent=styles["BodyText"], fontSize=9, leading=12, backColor=colors.HexColor("#fff4dc"), borderColor=colors.HexColor("#e09b24"), borderWidth=0.5, borderPadding=8, spaceBefore=6, spaceAfter=8))
    return styles


def _p(value: object, style) -> Paragraph:
    return Paragraph(_e(value), style)


def _pdf_table(headers: list[str], rows: list[list[object]], styles, widths=None) -> Table:
    cells = [[_p(x, styles["TableHeader"]) for x in headers]] + [[_p(x, styles["BodySmall"]) for x in row] for row in rows]
    table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b7c7ce")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def render_pdf(path: Path, data: dict, generated_at: datetime, version: int) -> None:
    styles = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm, topMargin=19 * mm, bottomMargin=18 * mm, title=f"AIGATOS Incident {data['incident_id']}", author="AIGATOS")

    def footer(c, document):
        c.saveState(); c.setStrokeColor(colors.HexColor("#b7c7ce")); c.line(17 * mm, 14 * mm, A4[0] - 17 * mm, 14 * mm)
        c.setFont("Helvetica", 7.5); c.setFillColor(colors.HexColor("#526373")); c.drawString(17 * mm, 9 * mm, "AIGATOS - Simulation contrôlée - Confidentiel")
        c.drawRightString(A4[0] - 17 * mm, 9 * mm, f"Page {document.page}"); c.restoreState()

    story = [Spacer(1, 25 * mm), _p("AIGATOS", styles["CoverTitle"]), _p("Rapport d'incident", styles["CoverSub"])]
    cover = [["Incident", data["incident_id"]], ["Workflow", data["workflow_id"]], ["Date UTC", _utc(generated_at)], ["Sévérité", data["severity"]], ["Statut", data["workflow_status"]], ["Source", data["explanation_source"]], ["Template", f"{TEMPLATE_VERSION} / version {version}"]]
    story += [_pdf_table(["Champ", "Valeur"], cover, styles, [42 * mm, 115 * mm]), Spacer(1, 18 * mm), _p("Ce rapport ne constitue pas une preuve de causalité confirmée.", styles["Notice"]), PageBreak()]
    story += [_p("1. Résumé exécutif", styles["Section"]), _pdf_table(["Véhicules", "Succès", "Échecs", "Rollbacks", "Taux", "Score"], [[data["vehicle_count"], data["success_count"], data["failure_count"], data["rollback_count"], f"{data['failure_rate']:.0%}", f"{data['global_confidence']:.6f}"]], styles), Spacer(1, 4 * mm), _p(data["incident_summary"], styles["BodySmall"]), _p(data["probable_root_cause"], styles["BodySmall"]), _p("Le score est déterministe et n'a pas été recalculé par un modèle génératif.", styles["Notice"])]
    timeline = [["Canary 1", "Exécutée"], ["Validation humaine", data["stage_one_approved_at"]], ["Canary 2", "30 véhicules - évaluation en attente"], ["Détection incident", data["incident_detected_at"]], ["Investigation multi-agent", data["investigation_completed_at"]], ["Validation humaine", data["workflow_status"]]]
    story += [_p("2. Chronologie Canary", styles["Section"]), _pdf_table(["Étape", "État / date UTC"], timeline, styles, [50 * mm, 107 * mm])]
    errors = [[x["hardware_revision"], x["error_code"], x["installation_step"], x["count"]] for x in data["normalized_errors"]]
    story += [_p("3. Analyse des erreurs", styles["Section"]), _pdf_table(["Matériel", "Erreur", "Étape", "Véhicules"], errors, styles, [30 * mm, 54 * mm, 50 * mm, 23 * mm])]
    story += [_p("4. Corrélations", styles["Section"]), _pdf_table(["Cohorte", "Échecs", "Taux"], [["HW_REV_B", "3/3", "100 %"], ["HW_REV_A", "3/27", "11,11 %"]], styles), _p(f"Risk ratio : {data['hw_b']['risk_ratio']:.1f}. IC 95 % : [{data['hw_b']['confidence_interval_95'][0]:.3f}, {data['hw_b']['confidence_interval_95'][1]:.3f}].", styles["BodySmall"]), _p("Corrélation ne signifie pas causalité.", styles["Notice"]), PageBreak()]
    story += [_p("5. Root Cause Analysis", styles["Section"]), _p(data["hypothesis"]["statement"], styles["BodySmall"]), _pdf_table(["Composante", "Valeur"], [list(x) for x in data["hypothesis"]["score_components"].items()], styles), _p("Hypothèses alternatives", styles["Subsection"])]
    story += [_p("• " + x, styles["BodySmall"]) for x in data["alternative_hypotheses"]] + [_p("Limitations", styles["Subsection"])] + [_p("• " + x, styles["BodySmall"]) for x in data["limitations"]] + [_p("anomaly_score=null", styles["BodySmall"])]
    story += [_p("6. Preuves", styles["Section"]), _p(f"Événements liés : {data['linked_event_count']}. Événements FAILURE : {data['failure_event_count']}. Aucune preuve inventée.", styles["BodySmall"]), _pdf_table(["evidence_id validé"], [[x] for x in data["evidence_ids"]], styles, [157 * mm])]
    actions = [[x["action"], x["status"], str(x["executed"]).lower()] for x in data["recommendations"]]
    story += [_p("7. Recommandations consultatives", styles["Section"]), _pdf_table(["Action", "Statut", "executed"], actions, styles, [95 * mm, 35 * mm, 27 * mm])]
    history = [[x["agent"], x["duration_ms"], x["status"]] for x in data["history"]]
    story += [PageBreak(), _p("8. Historique agentique", styles["Section"]), _pdf_table(["Agent", "Durée (ms)", "Statut"], history, styles, [60 * mm, 35 * mm, 62 * mm])]
    governance = [["Provider configuré", data["provider"]], ["Modèle", data["model"]], ["Appel", f"Timeout - {data['llm_duration_ms']} ms"], ["Source", data["explanation_source"]], ["Cache", "Cache hit enregistré"], ["Score", f"Inchangé : {data['global_confidence']:.6f}"], ["Décision du modèle", "Aucune"]]
    story += [_p("9. Gouvernance IA", styles["Section"]), _pdf_table(["Contrôle", "Valeur"], governance, styles, [55 * mm, 102 * mm]), _p("10. Validation humaine", styles["Section"]), _p("Décision :   [ ] Approve        [ ] Reject", styles["BodySmall"]), Spacer(1, 6 * mm), _p("Utilisateur : _________________________________________________", styles["BodySmall"]), Spacer(1, 6 * mm), _p("Date UTC : __________________________________________________", styles["BodySmall"]), Spacer(1, 6 * mm), _p("Commentaire :", styles["BodySmall"]), Spacer(1, 18 * mm), _p("________________________________________________________________________________", styles["BodySmall"]), Spacer(1, 8 * mm), _p("Aucune signature ou décision n'est préremplie.", styles["Notice"])]
    doc.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=partial(canvas.Canvas, invariant=1, pageCompression=1))
    path.write_bytes(output.getvalue())


def generate_report(db: Session, workflow_id: str, incident_id: str, explanation_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[IncidentReport, bool]:
    data = collect_report_data(db, workflow_id, incident_id, explanation_id)
    input_hash = hashlib.sha256(json.dumps({"template_version": TEMPLATE_VERSION, "data": data}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    existing = db.scalar(select(IncidentReport).where(IncidentReport.input_hash == input_hash))
    if existing is not None:
        path = Path(existing.pdf_path)
        if not path.exists() or _digest(path.read_bytes()) != existing.pdf_sha256:
            raise ReportValidationError("Archived PDF is missing or its hash changed")
        return existing, True
    version = (db.scalar(select(func.max(IncidentReport.version)).where(IncidentReport.incident_id == incident_id)) or 0) + 1
    generated_at = datetime.now(timezone.utc); output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"incident-{incident_id}-v{version}"; pdf_path = (output_dir / f"{stem}.pdf").resolve(); html_path = (output_dir / f"{stem}.html").resolve()
    rendered = render_html(data, generated_at, version); html_path.write_text(rendered, encoding="utf-8"); render_pdf(pdf_path, data, generated_at, version)
    report = IncidentReport(workflow_id=workflow_id, incident_id=incident_id, explanation_id=explanation_id, input_hash=input_hash, version=version, template_version=TEMPLATE_VERSION, pdf_path=str(pdf_path), html_path=str(html_path), pdf_sha256=_digest(pdf_path.read_bytes()), generated_at=generated_at)
    db.add(report); db.commit(); return report, False
