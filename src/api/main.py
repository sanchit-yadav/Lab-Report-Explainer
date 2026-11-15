"""FastAPI REST API Microservice for the AI Clinical Lab Report Explainer.

Exposes asynchronous document ingestion, status polling, clinical explanations,
conversational Q&A with guardrails, and Doctor Brief PDF downloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.api.models import (
    HealthResponse,
    JobStatus,
    JobStatusResponse,
    QARequest,
    QAResponse,
    UploadResponse,
)
from src.api.metrics import MetricsRegistry, PrometheusMiddleware
from src.health import run_health_check
from src.monitoring.sentry import init_sentry
from src.security.audit import SecurityAuditLogger
from src.security.scanner import FileSecurityScanner
from src.workers.job_manager import JobManager, JobRecord

logger = logging.getLogger("api")

# Initialize SRE Sentry monitoring with HIPAA PHI scrubber
init_sentry()

# Staging directory for uploaded patient reports
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 50MB file size ceiling
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

app = FastAPI(
    title="AI Clinical Lab Report Explainer API",
    version="1.0.0",
    description=(
        "Enterprise-grade clinical microservice providing 3-tier document extraction, "
        "deterministic range and panic flagging, clinical RAG over MedlinePlus guidelines, "
        "and bilingual patient explanations."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure Cross-Origin Resource Sharing (CORS) for web & mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to trusted client domains in production env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Prometheus telemetry metrics collection middleware
app.add_middleware(PrometheusMiddleware)


@app.get("/healthz", tags=["Diagnostics"], summary="Liveness Probe")
async def healthz() -> Dict[str, str]:
    """Lightweight Kubernetes / Docker liveness probe."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics", tags=["Diagnostics"], summary="Prometheus Telemetry Metrics")
async def get_metrics() -> Response:
    """Scrapes Prometheus metrics in standard exposition text format v0.0.4."""
    registry = MetricsRegistry.get_instance()
    return Response(
        content=registry.render_all(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/readyz", tags=["Diagnostics"], summary="Readiness Probe", response_model=HealthResponse)
async def readyz() -> HealthResponse:
    """Deep readiness probe verifying config, Gemini API credentials, and RAG embedders."""
    diagnostics = run_health_check()
    is_ready = diagnostics.get("status") == "healthy"

    resp = HealthResponse(
        status="ready" if is_ready else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        ready=is_ready,
        diagnostics=diagnostics,
    )

    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=resp.model_dump(),
        )
    return resp


@app.post(
    "/api/v1/reports/upload",
    tags=["Reports"],
    summary="Upload Laboratory Report",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
)
async def upload_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Laboratory report document (PDF, PNG, JPG, WEBP)"),
    explain_all: bool = Query(
        False, description="Whether to generate LLM explanations for normal biomarkers in addition to abnormal ones"
    ),
) -> UploadResponse:
    """Accepts a multipart file upload, validates extension & size, fingerprints SHA-256,

    and enqueues an asynchronous processing job.
    """
    filename = file.filename or "unknown_report.pdf"
    file_ext = Path(filename).suffix.lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file_ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read content in memory to validate size and compute SHA-256 fingerprint
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of 50MB ({file_size / (1024 * 1024):.2f}MB).",
        )

    file_hash = hashlib.sha256(content).hexdigest()

    # Pre-analytical security, malware, and exploit scan
    scanner = FileSecurityScanner(max_file_size_bytes=MAX_FILE_SIZE_BYTES)
    scan_res = scanner.scan_bytes(content, filename=filename)
    audit = SecurityAuditLogger.get_instance()

    if not scan_res.is_safe:
        MetricsRegistry.get_instance().guardrail_blocks_total.inc(reason="malware_scan")
        audit.log_event(
            event_type="MALWARE_SCAN_FAILED",
            actor_id="client_upload",
            resource_id=file_hash,
            details={"threat_type": scan_res.threat_type, "details": scan_res.details, "risk_score": scan_res.risk_score},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security check failed: {scan_res.details}",
        )

    audit.log_event(
        event_type="DOCUMENT_UPLOADED",
        actor_id="client_upload",
        resource_id=file_hash,
        details={"filename": filename, "file_size_bytes": file_size},
    )

    # Save to staging directory using hash for deduplication
    staged_path = UPLOAD_DIR / f"{file_hash}{file_ext}"
    if not staged_path.exists():
        staged_path.write_bytes(content)

    job_mgr = JobManager.get_instance()
    job_record = job_mgr.create_job(
        filename=filename,
        file_path=staged_path,
        file_hash=file_hash,
        file_size_bytes=file_size,
    )

    # Dispatch to background tasks for asynchronous non-blocking processing
    background_tasks.add_task(
        job_mgr.run_pipeline_job,
        job_record.job_id,
        explain_all,
    )

    return UploadResponse(
        job_id=job_record.job_id,
        file_hash=file_hash,
        filename=filename,
        file_size_bytes=file_size,
        status=job_record.status,
        message="Laboratory report accepted. Asynchronous processing pipeline dispatched.",
        created_at=job_record.created_at,
    )


@app.get(
    "/api/v1/reports/{job_id}/status",
    tags=["Reports"],
    summary="Get Processing Job Status",
    response_model=JobStatusResponse,
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll pipeline progress, completion percentage, and diagnostics for a job."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    return JobStatusResponse(
        job_id=record.job_id,
        file_hash=record.file_hash,
        filename=record.filename,
        status=record.status,
        progress_pct=record.progress_pct,
        current_step=record.current_step,
        created_at=record.created_at,
        completed_at=record.completed_at,
        patient_name=record.patient_name,
        total_tests=record.total_tests,
        flagged_count=record.flagged_count,
        panic_count=record.panic_count,
        error=record.error,
    )


@app.get(
    "/api/v1/reports/{job_id}/explanation",
    tags=["Reports"],
    summary="Get Report Clinical Explanation",
)
async def get_job_explanation(job_id: str) -> Dict[str, Any]:
    """Retrieve the full structured explanation payload once job status is 'ready'."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if record.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job failed during execution: {record.error}",
        )

    if record.status != JobStatus.READY or not record.explanation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is currently '{record.status}'. Result is not ready yet.",
        )

    return record.explanation.model_dump()


@app.post(
    "/api/v1/reports/{job_id}/qa",
    tags=["Reports"],
    summary="Ask Question About Lab Report",
    response_model=QAResponse,
)
async def ask_question_for_job(job_id: str, qa_req: QARequest) -> QAResponse:
    """Ask an educational clinical question contextualized with the patient's lab report."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    # Formulate patient context from completed report if available
    context_str = qa_req.patient_context or ""
    if not context_str and record.explanation:
        exp = record.explanation
        parts = [f"Patient: {exp.patient_name or 'Unknown'}"]
        if exp.raw_report and exp.raw_report.tests:
            parts.append("Key Biomarkers:")
            for t in exp.raw_report.tests:
                val_s = f"{t.value} {t.unit or ''}".strip()
                parts.append(f"- {t.test_name}: {val_s} [{t.flag.value.upper()}]")
        elif exp.test_explanations:
            parts.append("Key Biomarkers:")
            for t in exp.test_explanations:
                parts.append(f"- {t.test_name}: [{t.flag.value.upper()}]")
        context_str = "\n".join(parts)

    res = job_mgr.pipeline.answer_question(
        question=qa_req.question,
        patient_context=context_str if context_str else None,
        chat_history=qa_req.chat_history,
    )

    if res.get("blocked", False):
        MetricsRegistry.get_instance().guardrail_blocks_total.inc(
            reason=res.get("category") or "adversarial"
        )

    SecurityAuditLogger.get_instance().log_event(
        event_type="QA_QUERY_PROCESSED",
        actor_id="client_qa",
        resource_id=job_id,
        details={"question_len": len(qa_req.question), "blocked": res.get("blocked", False)},
    )

    return QAResponse(
        job_id=job_id,
        blocked=res.get("blocked", False),
        category=res.get("category"),
        answer_en=res.get("answer_en", ""),
        answer_hi=res.get("answer_hi", ""),
        source_urls=res.get("source_urls", []),
        disclaimer=res.get("disclaimer", ""),
        elapsed_ms=res.get("elapsed_ms", 0.0),
    )


@app.get(
    "/api/v1/reports/{job_id}/pdf",
    tags=["Reports"],
    summary="Download Doctor Brief PDF",
)
async def download_doctor_brief_pdf(job_id: str) -> Response:
    """Download the Doctor Discussion Brief PDF generated for the patient."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if record.status != JobStatus.READY or not record.pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PDF for job '{job_id}' is not ready (status: {record.status}).",
        )

    clean_filename = f"doctor_brief_{record.job_id[:8]}.pdf"
    SecurityAuditLogger.get_instance().log_event(
        event_type="PDF_DOWNLOADED",
        actor_id="client_download",
        resource_id=record.job_id,
        details={"filename": clean_filename, "file_hash": record.file_hash},
    )
    return Response(
        content=record.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{clean_filename}"',
            "Content-Type": "application/pdf",
        },
    )


@app.get(
    "/api/v1/reports",
    tags=["Reports"],
    summary="List Recent Processing Jobs",
    response_model=List[JobStatusResponse],
)
async def list_recent_jobs(limit: int = Query(50, ge=1, le=200)) -> List[JobStatusResponse]:
    """List recent laboratory report jobs."""
    job_mgr = JobManager.get_instance()
    records = job_mgr.list_jobs(limit=limit)

    return [
        JobStatusResponse(
            job_id=r.job_id,
            file_hash=r.file_hash,
            filename=r.filename,
            status=r.status,
            progress_pct=r.progress_pct,
            current_step=r.current_step,
            created_at=r.created_at,
            completed_at=r.completed_at,
            patient_name=r.patient_name,
            total_tests=r.total_tests,
            flagged_count=r.flagged_count,
            panic_count=r.panic_count,
            error=r.error,
        )
        for r in records
    ]


@app.get(
    "/api/v1/audit/verify",
    tags=["Security & Compliance"],
    summary="Verify Audit Trail Cryptographic Integrity",
)
async def verify_audit_trail() -> Dict[str, Any]:
    """Verify cryptographic SHA-256 hash chaining of all HIPAA audit trail entries."""
    audit = SecurityAuditLogger.get_instance()
    is_valid, err = audit.verify_integrity()
    return {
        "valid": is_valid,
        "latest_hash": audit.latest_hash,
        "error": err,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/api/v1/audit/logs",
    tags=["Security & Compliance"],
    summary="Inspect Audit Trail Records",
)
async def get_audit_logs(limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    """Query recent immutable audit trail records for HIPAA compliance inspection."""
    from dataclasses import asdict
    audit = SecurityAuditLogger.get_instance()
    records = audit.get_records(limit=limit)
    return [asdict(r) for r in records]


@app.get(
    "/api/v1/reports/{job_id}/fhir",
    tags=["Interoperability & EHR"],
    summary="Export Report as HL7 FHIR R4 Bundle",
)
async def get_job_fhir_bundle(job_id: str) -> Dict[str, Any]:
    """Export the laboratory evaluation as an official HL7 FHIR R4 Bundle (DiagnosticReport + Observations)."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if record.status != JobStatus.READY or not record.explanation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"FHIR bundle for job '{job_id}' is not ready (status: {record.status}).",
        )

    from src.extraction.schema import LabReport, TestResult
    from src.interop.fhir_export import FHIRExporter

    report_obj = record.extracted_report or (record.explanation.raw_report if record.explanation else None)
    if not report_obj:
        tests_list = [
            TestResult(
                test_name=t.test_name,
                flag=t.flag,
            )
            for t in record.explanation.test_explanations
        ]
        report_obj = LabReport(
            patient_name=record.patient_name,
            tests=tests_list,
        )

    SecurityAuditLogger.get_instance().log_event(
        event_type="FHIR_BUNDLE_EXPORTED",
        actor_id="ehr_gateway",
        resource_id=job_id,
        details={"patient_name": record.patient_name, "test_count": len(report_obj.tests)},
    )

    bundle = FHIRExporter.create_diagnostic_report(
        report_obj,
        explanation=record.explanation,
        pdf_bytes=record.pdf_bytes,
    )
    return bundle
