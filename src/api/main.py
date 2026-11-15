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
from src.health import run_health_check
from src.workers.job_manager import JobManager, JobRecord

logger = logging.getLogger("api")

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


@app.get("/healthz", tags=["Diagnostics"], summary="Liveness Probe")
async def healthz() -> Dict[str, str]:
    """Lightweight Kubernetes / Docker liveness probe."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


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
        if exp.test_explanations:
            parts.append("Key Biomarkers:")
            for t in exp.test_explanations:
                val_s = f"{t.value} {t.unit or ''}".strip()
                parts.append(f"- {t.test_name}: {val_s} [{t.flag.value.upper()}]")
        context_str = "\n".join(parts)

    res = job_mgr.pipeline.answer_question(
        question=qa_req.question,
        patient_context=context_str if context_str else None,
        chat_history=qa_req.chat_history,
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
