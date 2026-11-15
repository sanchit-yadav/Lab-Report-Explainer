"""Pydantic schemas and models for the FastAPI REST API microservice."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Lifecycle stages for asynchronous report processing jobs."""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    FLAGGING = "flagging"
    RAG_RETRIEVAL = "rag_retrieval"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class UploadResponse(BaseModel):
    """Response returned upon accepting a laboratory document upload."""
    job_id: str = Field(..., description="Unique UUID tracking the processing job")
    file_hash: str = Field(..., description="SHA-256 fingerprint for document deduplication")
    filename: str = Field(..., description="Original filename of the uploaded report")
    file_size_bytes: int = Field(..., description="Size of the uploaded file in bytes")
    status: JobStatus = Field(JobStatus.QUEUED, description="Initial job status")
    message: str = Field(..., description="Human-readable status summary")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class JobStatusResponse(BaseModel):
    """Detailed progress and diagnostic telemetry for an asynchronous job."""
    job_id: str
    file_hash: str
    filename: str
    status: JobStatus
    progress_pct: int = Field(0, ge=0, le=100, description="Pipeline progress percentage (0-100)")
    current_step: str = Field("queued", description="Human-readable pipeline phase description")
    created_at: str
    completed_at: Optional[str] = None
    patient_name: Optional[str] = None
    total_tests: Optional[int] = None
    flagged_count: Optional[int] = None
    panic_count: Optional[int] = None
    error: Optional[str] = None


class QARequest(BaseModel):
    """Request payload for conversational clinical Q&A."""
    question: str = Field(..., min_length=2, max_length=1000, description="User educational inquiry")
    patient_context: Optional[str] = Field(None, description="Optional serialized patient biomarker context")
    chat_history: Optional[List[Dict[str, str]]] = Field(
        None, description="Optional multi-turn chat history [{'role': 'user', 'content': '...'}]"
    )


class QAResponse(BaseModel):
    """Guardrail-validated response payload for clinical inquiries."""
    job_id: Optional[str] = None
    blocked: bool = Field(False, description="Whether Layer 1 input guardrails blocked the inquiry")
    category: Optional[str] = Field(None, description="Guardrail violation category if blocked")
    answer_en: str
    answer_hi: str
    source_urls: List[str] = Field(default_factory=list, description="Grounding clinical guideline citations")
    disclaimer: str
    elapsed_ms: float = 0.0


class HealthResponse(BaseModel):
    """System diagnostic and readiness health check response."""
    status: str
    timestamp: str
    ready: bool
    diagnostics: Dict[str, Any]
