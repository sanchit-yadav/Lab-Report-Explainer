"""Pydantic schemas and models for the FastAPI REST API microservice."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    """Lifecycle stages for asynchronous report processing jobs."""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    REVIEW_NEEDED = "review_needed"
    FLAGGING = "flagging"
    RAG_RETRIEVAL = "rag_retrieval"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


class UserRegisterRequest(BaseModel):
    """Payload for registering a new user account."""
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., min_length=8, max_length=128, description="Account password (min 8 characters)")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name of the user")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not EMAIL_REGEX.match(v_clean):
            raise ValueError("Invalid email address format.")
        return v_clean


class UserLoginRequest(BaseModel):
    """Payload for user authentication."""
    email: str = Field(..., description="Account email address")
    password: str = Field(..., description="Account password")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not EMAIL_REGEX.match(v_clean):
            raise ValueError("Invalid email address format.")
        return v_clean


class UserResponse(BaseModel):
    """Public user profile model."""
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT bearer token and authenticated user profile response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


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


class ConfirmBiomarkerPayload(BaseModel):
    """Biomarker test entry confirmed or edited by user."""
    test_name: str
    value: Optional[float] = None
    raw_value: Optional[str] = None
    unit: Optional[str] = None
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    ref_raw: Optional[str] = None
    flag: Optional[str] = None


class ConfirmReportRequest(BaseModel):
    """Request payload to confirm or correct extracted lab parameters."""
    patient_name: Optional[str] = None
    tests: List[ConfirmBiomarkerPayload] = Field(default_factory=list)
    explain_all: bool = False


class ConfirmReportResponse(BaseModel):
    """Response returned upon confirming report parameters."""
    job_id: str
    status: JobStatus
    message: str
    confirmed_tests_count: int


class ExtractedReportResponse(BaseModel):
    """Structured laboratory data extracted from document for human review."""
    job_id: str
    patient_name: Optional[str] = None
    total_tests: int
    tests: List[Dict[str, Any]]
