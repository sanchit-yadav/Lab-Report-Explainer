"""FastAPI REST API Microservice for the AI Clinical Lab Report Explainer.

Exposes asynchronous document ingestion, status polling, clinical explanations,
conversational Q&A with guardrails, and Doctor Brief PDF downloads.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.api.auth import get_current_user, get_optional_current_user, validate_jwt_security
from src.api.models import (
    ConfirmReportRequest,
    ConfirmReportResponse,
    ExtractedReportResponse,
    HealthResponse,
    JobStatus,
    JobStatusResponse,
    QARequest,
    QAResponse,
    UploadResponse,
)
from src.api.metrics import MetricsRegistry, PrometheusMiddleware
from src.api.routes.auth import router as auth_router
from src.db.models import User
from src.db.session import init_db
from src.health import run_health_check
from src.monitoring.sentry import init_sentry
from src.security.audit import SecurityAuditLogger
from src.security.rate_limiter import SlidingWindowRateLimiter
from src.security.scanner import FileSecurityScanner
from src.workers.job_manager import JobManager, JobRecord

logger = logging.getLogger("api")

# Initialize SRE Sentry monitoring with HIPAA PHI scrubber
init_sentry()

# 30 upload requests per minute per IP to protect against resource exhaustion / DoS
upload_rate_limiter = SlidingWindowRateLimiter(times=30, seconds=60, name="reports_upload")

# Staging directory for uploaded patient reports
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 50MB file size ceiling (overridable via MAX_FILE_SIZE_MB env var)
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
ALLOWED_EXTENSIONS = set(os.environ.get("ALLOWED_EXTENSIONS", ".pdf,.png,.jpg,.jpeg,.webp").split(","))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to handle startup and shutdown sequences."""
    validate_jwt_security()
    try:
        init_db()
        logger.info("Relational database schema initialized successfully.")
    except Exception as exc:
        logger.error(f"Error during relational database initialization: {exc}")
    yield


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
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS) restricted to trusted web & mobile clients
allowed_origins_env = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:8501,http://127.0.0.1:8501,http://localhost:8000",
)
cors_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Prometheus telemetry metrics collection middleware
app.add_middleware(PrometheusMiddleware)

# Include Authentication & User Management Router
app.include_router(auth_router)


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
    dependencies=[Depends(upload_rate_limiter)],
)
async def upload_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Laboratory report document (PDF, PNG, JPG, WEBP)"),
    explain_all: bool = Query(
        False, description="Whether to generate LLM explanations for normal biomarkers in addition to abnormal ones"
    ),
    auto_confirm: bool = Query(
        True, description="Whether to automatically confirm and explain immediately without pausing for review"
    ),
    current_user: Optional[User] = Depends(get_optional_current_user),
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
        user_id=current_user.id if current_user else None,
    )

    # Dispatch to background tasks for asynchronous non-blocking processing
    background_tasks.add_task(
        job_mgr.run_pipeline_job,
        job_record.job_id,
        explain_all,
        auto_confirm,
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


def _clean_float(val: Any) -> Optional[float]:
    """Safely convert numeric values to JSON-compliant floats, mapping NaN/inf to None."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


@app.get(
    "/api/v1/reports/{job_id}/extracted",
    tags=["Reports"],
    summary="Get Extracted Lab Biomarkers For Human Review",
    response_model=ExtractedReportResponse,
)
async def get_extracted_report(job_id: str) -> ExtractedReportResponse:
    """Retrieve raw extracted biomarkers to support human-in-the-loop inspection and editing."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if not record.extracted_report:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Extraction is not ready for job '{job_id}' (current status: {record.status}).",
        )

    tests_list = []
    for t in getattr(record.extracted_report, "tests", []):
        tests_list.append(
            {
                "test_name": t.test_name,
                "value": _clean_float(t.value),
                "raw_value": t.raw_value or "",
                "unit": t.unit or "",
                "ref_low": _clean_float(t.ref_low),
                "ref_high": _clean_float(t.ref_high),
                "ref_raw": t.ref_raw or "",
                "flag": t.flag.value if hasattr(t.flag, "value") else str(t.flag),
                "loinc_code": t.loinc_code,
                "category": t.category,
            }
        )

    return ExtractedReportResponse(
        job_id=job_id,
        patient_name=record.patient_name,
        total_tests=len(tests_list),
        tests=tests_list,
    )


@app.post(
    "/api/v1/reports/{job_id}/confirm",
    tags=["Reports"],
    summary="Confirm or Correct Extracted Parameters and Trigger Explanations",
    response_model=ConfirmReportResponse,
)
async def confirm_report(
    job_id: str,
    req: ConfirmReportRequest,
    background_tasks: BackgroundTasks,
) -> ConfirmReportResponse:
    """Accept verified/corrected parameters and resume explanation generation."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if not req.tests:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one test parameter is required to confirm a report.",
        )

    from src.extraction.schema import FlagStatus, LabReport, TestResult

    updated_tests = []
    for p in req.tests:
        val_clean = _clean_float(p.value)
        ref_low_clean = _clean_float(p.ref_low)
        ref_high_clean = _clean_float(p.ref_high)

        flag_val = FlagStatus.UNKNOWN
        if p.flag:
            try:
                flag_val = FlagStatus(p.flag.lower())
            except ValueError:
                flag_val = FlagStatus.UNKNOWN
        elif val_clean is not None and ref_low_clean is not None and ref_high_clean is not None:
            if val_clean < ref_low_clean:
                flag_val = FlagStatus.LOW
            elif val_clean > ref_high_clean:
                flag_val = FlagStatus.HIGH
            else:
                flag_val = FlagStatus.NORMAL

        test_res = TestResult(
            test_name=p.test_name,
            value=val_clean,
            raw_value=p.raw_value or (str(val_clean) if val_clean is not None else ""),
            unit=p.unit or "",
            ref_low=ref_low_clean,
            ref_high=ref_high_clean,
            ref_raw=p.ref_raw or (f"{ref_low_clean} - {ref_high_clean}" if ref_low_clean is not None and ref_high_clean is not None else ""),
            flag=flag_val,
        )
        updated_tests.append(test_res)

    confirmed_lab_report = LabReport(
        patient_name=req.patient_name or record.patient_name,
        tests=updated_tests,
    )

    # Dispatch to background tasks to resume explanation generation
    background_tasks.add_task(
        job_mgr.confirm_and_explain_job,
        job_id,
        confirmed_lab_report,
        req.explain_all,
    )

    return ConfirmReportResponse(
        job_id=job_id,
        status=JobStatus.FLAGGING,
        message="Parameters confirmed. Clinical explanations and Doctor Brief generation dispatched.",
        confirmed_tests_count=len(updated_tests),
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report processing failed: {record.error or 'Unknown error'}",
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

    if record.status != JobStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PDF for job '{job_id}' is not ready (status: {record.status}).",
        )

    # If pdf_bytes not in memory, dynamically re-generate from explanation
    if not record.pdf_bytes and record.explanation:
        try:
            from src.explainer.pdf_export import generate_doctor_brief_pdf
            record.pdf_bytes = generate_doctor_brief_pdf(record.explanation)
        except Exception as pdf_gen_err:
            logger.warning(f"Could not re-generate Doctor Brief PDF for job {job_id}: {pdf_gen_err}")

    if not record.pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PDF for job '{job_id}' could not be generated or loaded.",
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
async def list_recent_jobs(
    limit: int = Query(50, ge=1, le=200),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> List[JobStatusResponse]:
    """List recent laboratory report jobs, scoped to current user if authenticated."""
    job_mgr = JobManager.get_instance()
    records = job_mgr.list_jobs(
        limit=limit,
        user_id=current_user.id if current_user else None,
    )

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


@app.delete(
    "/api/v1/reports/{job_id}",
    tags=["Reports"],
    summary="Delete Laboratory Report",
    status_code=status.HTTP_200_OK,
)
async def delete_report(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Permanently delete a laboratory report and its associated biomarker observations.

    Ensures strict user isolation: regular users may only delete their own reports,
    while administrative users can delete any report.
    """
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{job_id}' not found.",
        )

    # Authorization check
    if current_user.role != "admin" and record.user_id and record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this report.",
        )

    target_user_id = None if current_user.role == "admin" else current_user.id
    success = job_mgr.delete_job(job_id=job_id, user_id=target_user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{job_id}' could not be deleted.",
        )

    SecurityAuditLogger.get_instance().log_event(
        event_type="REPORT_DELETED",
        actor_id=current_user.id,
        resource_id=job_id,
        details={"filename": record.filename, "file_hash": record.file_hash},
    )

    return {
        "job_id": job_id,
        "status": "deleted",
        "message": f"Report '{record.filename}' and all associated test records were permanently deleted.",
    }


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


# Mount React Modern Frontend if built
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
frontend_dist = _PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


