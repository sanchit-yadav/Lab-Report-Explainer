"""Typed input and output Pydantic schemas for each modular pipeline stage."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from src.extraction.schema import FlagStatus, LabReport, TestResult


def generate_request_id() -> str:
    """Generate canonical request tracking UUID."""
    return str(uuid.uuid4())


# ==============================================================================
# Stage 1: validate_upload
# ==============================================================================

class ValidateUploadInput(BaseModel):
    """Input payload for document upload security validation and sanitization."""
    file_bytes: bytes
    filename: str
    request_id: str = Field(default_factory=generate_request_id)
    max_file_size_bytes: int = 25 * 1024 * 1024


class ValidateUploadOutput(BaseModel):
    """Output from upload validation verifying magic bytes, structure, and security."""
    request_id: str
    is_valid: bool
    file_hash: str
    filename: str
    file_size_bytes: int
    mime_type: str
    page_count: Optional[int] = None
    sanitized_bytes: bytes
    error: Optional[str] = None


# ==============================================================================
# Stage 2: ocr_parse
# ==============================================================================

class OCRLine(BaseModel):
    """Parsed single line of text with optional spatial bounding box."""
    line_num: int
    text: str
    bbox: Optional[List[float]] = None  # [x0, top, x1, bottom]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")


class OCRPage(BaseModel):
    """Extracted content from an individual document page."""
    page_num: int
    text: str
    lines: List[OCRLine] = Field(default_factory=list)
    tables: List[List[List[str]]] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    needs_clearer_image: bool = False
    advisory: Optional[str] = None


class OCRParseInput(BaseModel):
    """Input for document text and layout extraction."""
    file_bytes: bytes
    filename: str
    request_id: str = Field(default_factory=generate_request_id)


class OCRParseOutput(BaseModel):
    """Extracted text, geometry, and tables across all pages."""
    request_id: str
    full_text: str
    pages: List[OCRPage] = Field(default_factory=list)
    total_pages: int = 0
    parsing_tier: int = 1
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    needs_clearer_image: bool = False
    advisory: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Stage 3: extract_values
# ==============================================================================

class ExtractionOutputItem(BaseModel):
    """Standardized analyte observation adhering to the clinical portfolio schema.
    
    Fields:
      test_name: Canonical analyte identifier
      value: Numeric measurement or None if non-numeric
      unit: Standard measurement unit
      ref_low: Reference interval lower bound
      ref_high: Reference interval upper bound
      flag: Deterministic flag (low/normal/high/critical)
      source_page: 1-indexed document page number
      source_bbox_or_line: Bounding box or line reference
      confidence: Extraction confidence score (0.0 to 1.0)
    """
    test_name: str
    value: Optional[float] = None
    unit: str = ""
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    flag: FlagStatus = FlagStatus.UNKNOWN
    source_page: int = 1
    source_location: Optional[str] = None
    source_bbox_or_line: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_value: str = ""
    ref_raw: str = ""
    loinc_code: Optional[str] = None
    loinc_name: Optional[str] = None
    category: Optional[str] = None

    def to_test_result(self) -> TestResult:
        """Convert to internal TestResult schema for backward compatibility."""
        return TestResult(
            test_name=self.test_name,
            value=self.value,
            raw_value=self.raw_value or (str(self.value) if self.value is not None else ""),
            unit=self.unit,
            ref_low=self.ref_low,
            ref_high=self.ref_high,
            ref_raw=self.ref_raw or (f"{self.ref_low} - {self.ref_high}" if self.ref_low is not None and self.ref_high is not None else ""),
            flag=self.flag,
            source_page=self.source_page,
            source_bbox_or_line=self.source_bbox_or_line,
            confidence=self.confidence,
            loinc_code=self.loinc_code,
            loinc_name=self.loinc_name,
            category=self.category,
        )

    @classmethod
    def from_test_result(cls, tr: TestResult) -> ExtractionOutputItem:
        """Construct from existing TestResult model."""
        return cls(
            test_name=tr.test_name,
            value=tr.value,
            unit=tr.unit or "",
            ref_low=tr.ref_low,
            ref_high=tr.ref_high,
            flag=tr.flag if isinstance(tr.flag, FlagStatus) else FlagStatus(str(tr.flag).lower()),
            source_page=getattr(tr, "source_page", 1),
            source_bbox_or_line=getattr(tr, "source_bbox_or_line", None),
            confidence=getattr(tr, "confidence", 1.0),
            raw_value=tr.raw_value or "",
            ref_raw=tr.ref_raw or "",
            loinc_code=tr.loinc_code,
            loinc_name=tr.loinc_name,
            category=tr.category,
        )


class ExtractValuesInput(BaseModel):
    """Input for biomarker tabular and value extraction."""
    parsed_doc: OCRParseOutput
    raw_bytes: Optional[bytes] = None
    request_id: str = Field(default_factory=generate_request_id)
    patient_name_hint: Optional[str] = None


class ExtractValuesOutput(BaseModel):
    """Structured clinical report representation with deterministically assigned flags."""
    request_id: str
    patient_name: Optional[str] = None
    patient_age: Optional[str] = None
    patient_gender: Optional[str] = None
    report_date: Optional[str] = None
    lab_name: Optional[str] = None
    items: List[ExtractionOutputItem] = Field(default_factory=list)
    flagged_count: int = 0
    critical_count: int = 0
    extraction_method: str = "pdfplumber"
    needs_better_upload: bool = False
    implausible_findings: List[str] = Field(default_factory=list)
    plausibility_advisory: Optional[str] = None

    def to_lab_report(self) -> LabReport:
        """Convert to internal LabReport domain model."""
        return LabReport(
            patient_name=self.patient_name,
            patient_age=self.patient_age,
            patient_gender=self.patient_gender,
            report_date=self.report_date,
            lab_name=self.lab_name,
            tests=[item.to_test_result() for item in self.items],
            extraction_method=self.extraction_method,
        )


# ==============================================================================
# Stage 4: retrieve
# ==============================================================================

class RetrievedChunk(BaseModel):
    """Individual retrieved and reranked clinical reference knowledge chunk."""
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float
    source_url: Optional[str] = None


class RetrieveInput(BaseModel):
    """Input payload for RAG retrieval."""
    request_id: str = Field(default_factory=generate_request_id)
    queries: List[str]
    top_k: int = 3
    top_n: int = 2


class RetrieveOutput(BaseModel):
    """Collection of retrieved clinical guidelines mapped by analyte query."""
    request_id: str
    chunks_by_query: Dict[str, List[RetrievedChunk]] = Field(default_factory=dict)
    total_chunks: int = 0


# ==============================================================================
# Stage 5: explain
# ==============================================================================

from src.citations.models import AttributedClaim

class TestExplanationItem(BaseModel):
    """Bilingual educational explanation for an individual biomarker."""
    test_name: str
    value_display: str
    flag: FlagStatus
    explanation_en: str
    explanation_hi: str
    clinical_significance: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list)
    claims: List[AttributedClaim] = Field(default_factory=list)
    sources: Dict[str, Any] = Field(default_factory=dict)
    citation_accuracy_score: float = 1.0
    grounding_status: str = "FULLY_GROUNDED"
    bibliography: Optional[str] = None
    ui_citation_payload: Optional[Dict[str, Any]] = None


class ExplainInput(BaseModel):
    """Input for synthesizing patient-facing explanations."""
    request_id: str = Field(default_factory=generate_request_id)
    extraction: ExtractValuesOutput
    retrieved_knowledge: RetrieveOutput
    language: str = "en"
    explain_all: bool = False


class ExplainOutput(BaseModel):
    """Assembled bilingual clinical explanations prior to final guardrail sanitization."""
    request_id: str
    patient_name: Optional[str] = None
    summary_en: str
    summary_hi: str
    test_explanations: List[TestExplanationItem] = Field(default_factory=list)
    flagged_count: int = 0
    total_tests: int = 0
    disclaimer: str = ""


# ==============================================================================
# Stage 6: output_guard
# ==============================================================================

class OutputGuardInput(BaseModel):
    """Input payload for Layer 3 output guardrails."""
    request_id: str = Field(default_factory=generate_request_id)
    explanation: ExplainOutput
    extracted_items: List[ExtractionOutputItem] = Field(default_factory=list)
    language: str = "en"


class OutputGuardOutput(BaseModel):
    """Sanitized, safety-verified clinical explanation safe for patient presentation."""
    request_id: str
    is_safe: bool = True
    sanitized_summary_en: str
    sanitized_summary_hi: str
    sanitized_explanations: List[TestExplanationItem] = Field(default_factory=list)
    violations_detected: int = 0
    numerical_discrepancies: List[str] = Field(default_factory=list)
    citation_accuracy: float = 1.0
    total_verified_citations: int = 0
    disclaimer: str
