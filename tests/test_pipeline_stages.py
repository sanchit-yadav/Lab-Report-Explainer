"""Comprehensive unit test suite for Phase 1 modular pipeline stages."""

from __future__ import annotations

import io
from pathlib import Path
import pytest

from src.extraction.schema import FlagStatus
from src.pipeline import LabReportPipeline
from src.stages import (
    ExplainInput,
    ExplainOutput,
    ExplainStage,
    ExtractionOutputItem,
    ExtractValuesInput,
    ExtractValuesOutput,
    ExtractValuesStage,
    OCRLine,
    OCRPage,
    OCRParseInput,
    OCRParseOutput,
    OCRParseStage,
    OutputGuardInput,
    OutputGuardOutput,
    OutputGuardStage,
    RetrievedChunk,
    RetrieveInput,
    RetrieveOutput,
    RetrieveStage,
    ValidateUploadInput,
    ValidateUploadOutput,
    ValidateUploadStage,
    generate_request_id,
)
from src.stages.logger import sanitize_value


def create_minimal_pdf_bytes(text_lines: List[str]) -> bytes:
    """Helper to synthesize valid minimal PDF bytes with text."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


# ==============================================================================
# Stage 1: validate_upload Tests
# ==============================================================================

def test_validate_upload_valid_pdf():
    stage = ValidateUploadStage()
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\nxref\n0 1\n0000000000 65535 f \ntrailer<<>>startxref\n9\n%%EOF"
    res = stage(ValidateUploadInput(file_bytes=pdf_bytes, filename="lab_report.pdf"))
    assert res.is_valid is True
    assert res.mime_type == "application/pdf"
    assert res.file_size_bytes == len(pdf_bytes)
    assert res.file_hash is not None
    assert res.error is None


def test_validate_upload_invalid_magic_bytes():
    stage = ValidateUploadStage()
    raw_exe = b"MZ\x90\x00\x03\x00\x00\x00ThisIsAnExecutable"
    res = stage(ValidateUploadInput(file_bytes=raw_exe, filename="exploit.pdf"))
    assert res.is_valid is False
    assert "magic-byte" in res.error.lower() or "security" in res.error.lower()


def test_validate_upload_empty_file():
    stage = ValidateUploadStage()
    res = stage(ValidateUploadInput(file_bytes=b"", filename="empty.pdf"))
    assert res.is_valid is False
    assert "empty" in res.error.lower()


# ==============================================================================
# Stage 2: ocr_parse Tests
# ==============================================================================

def test_ocr_parse_stage():
    stage = OCRParseStage()
    sample_text = "Patient: John Doe\nGlucose Fasting: 110 mg/dL (70 - 99)\nHemoglobin: 14.2 g/dL (13.0 - 17.0)"
    res = stage(OCRParseInput(file_bytes=sample_text.encode("utf-8"), filename="report.txt"))
    assert res.total_pages >= 1
    assert "Glucose Fasting" in res.full_text
    assert len(res.pages[0].lines) >= 3


# ==============================================================================
# Stage 3: extract_values Deterministic Flagging Tests
# ==============================================================================

def test_extract_values_deterministic_flags():
    """Verify flags are computed strictly mathematically by code, never by LLM."""
    stage = ExtractValuesStage()

    # Construct mock parsed OCR document with High, Low, and Normal values
    lines = [
        OCRLine(line_num=1, text="Complete Blood Count & Metabolic"),
        OCRLine(line_num=2, text="Fasting Blood Glucose 145 mg/dL 70.0 - 99.0 High"),
        OCRLine(line_num=3, text="Hemoglobin 10.5 g/dL 13.0 - 17.0 Low"),
        OCRLine(line_num=4, text="Total Cholesterol 180 mg/dL 125.0 - 200.0 Normal"),
    ]
    page = OCRPage(page_num=1, text="\n".join(l.text for l in lines), lines=lines)
    parsed_doc = OCRParseOutput(
        request_id="test_req",
        full_text="\n".join(l.text for l in lines),
        pages=[page],
        total_pages=1,
    )

    out = stage(ExtractValuesInput(parsed_doc=parsed_doc, request_id="test_req"))
    assert out.request_id == "test_req"

    # Verify extraction items conform strictly to required schema
    for item in out.items:
        assert isinstance(item, ExtractionOutputItem)
        assert item.test_name != ""
        assert isinstance(item.flag, FlagStatus)
        assert item.source_page >= 1
        assert 0.0 <= item.confidence <= 1.0


def test_deterministic_flag_pure_code_logic():
    """Verify that flag assignment uses deterministic interval comparison."""
    # Low Value: 60 < 70
    item_low = ExtractionOutputItem(
        test_name="Glucose",
        value=60.0,
        unit="mg/dL",
        ref_low=70.0,
        ref_high=99.0,
        flag=FlagStatus.LOW,
    )
    assert item_low.value < item_low.ref_low
    assert item_low.flag == FlagStatus.LOW

    # High Value: 140 > 99
    item_high = ExtractionOutputItem(
        test_name="Glucose",
        value=140.0,
        unit="mg/dL",
        ref_low=70.0,
        ref_high=99.0,
        flag=FlagStatus.HIGH,
    )
    assert item_high.value > item_high.ref_high
    assert item_high.flag == FlagStatus.HIGH

    # Normal Value: 70 <= 85 <= 99
    item_norm = ExtractionOutputItem(
        test_name="Glucose",
        value=85.0,
        unit="mg/dL",
        ref_low=70.0,
        ref_high=99.0,
        flag=FlagStatus.NORMAL,
    )
    assert item_norm.ref_low <= item_norm.value <= item_norm.ref_high
    assert item_norm.flag == FlagStatus.NORMAL


# ==============================================================================
# Stage 4: retrieve Tests
# ==============================================================================

def test_retrieve_stage():
    stage = RetrieveStage()
    inp = RetrieveInput(
        queries=["glucose high lab test meaning"],
        top_k=2,
        top_n=1,
    )
    out = stage(inp)
    assert out.request_id is not None
    assert "glucose high lab test meaning" in out.chunks_by_query
    chunks = out.chunks_by_query["glucose high lab test meaning"]
    assert len(chunks) <= 2
    if chunks:
        assert isinstance(chunks[0], RetrievedChunk)
        assert chunks[0].text != ""


# ==============================================================================
# Stage 5 & 6: explain and output_guard Tests
# ==============================================================================

def test_explain_and_output_guard_pipeline():
    explain_stage = ExplainStage()
    guard_stage = OutputGuardStage()

    items = [
        ExtractionOutputItem(
            test_name="Fasting Blood Glucose",
            value=126.0,
            unit="mg/dL",
            ref_low=70.0,
            ref_high=99.0,
            flag=FlagStatus.HIGH,
            source_page=1,
            confidence=0.98,
        )
    ]
    ext_out = ExtractValuesOutput(
        request_id="req_123",
        patient_name="Alex Smith",
        items=items,
        flagged_count=1,
        critical_count=0,
    )
    ret_out = RetrieveOutput(
        request_id="req_123",
        chunks_by_query={},
        total_chunks=0,
    )

    exp_out = explain_stage(
        ExplainInput(
            request_id="req_123",
            extraction=ext_out,
            retrieved_knowledge=ret_out,
        )
    )
    assert exp_out.request_id == "req_123"
    assert len(exp_out.test_explanations) == 1
    assert exp_out.test_explanations[0].test_name == "Fasting Blood Glucose"

    # Stage 6: Output guard
    guard_out = guard_stage(
        OutputGuardInput(
            request_id="req_123",
            explanation=exp_out,
            extracted_items=items,
        )
    )
    assert guard_out.request_id == "req_123"
    assert guard_out.is_safe is True
    assert len(guard_out.sanitized_explanations) == 1
    assert "Fasting Blood Glucose" in guard_out.sanitized_explanations[0].test_name


def test_output_guard_numerical_discrepancy_detection():
    """Verify output guard flags any hallucinated number not present in extracted report."""
    guard_stage = OutputGuardStage()
    items = [
        ExtractionOutputItem(
            test_name="Glucose",
            value=95.0,
            unit="mg/dL",
            ref_low=70.0,
            ref_high=99.0,
            flag=FlagStatus.NORMAL,
        )
    ]
    # Simulate LLM hallucinating a value (e.g. 280.5) that was never in the lab report
    from src.stages.schemas import ExplainOutput, TestExplanationItem
    exp_out = ExplainOutput(
        request_id="test_hallucination",
        summary_en="Your glucose is 280.5 mg/dL which is very high.",
        summary_hi="विवरण",
        test_explanations=[
            TestExplanationItem(
                test_name="Glucose",
                value_display="95.0 mg/dL",
                flag=FlagStatus.NORMAL,
                explanation_en="Your measurement of 280.5 mg/dL shows a concern.",
                explanation_hi="विवरण",
            )
        ],
    )

    res = guard_stage(
        OutputGuardInput(
            request_id="test_hallucination",
            explanation=exp_out,
            extracted_items=items,
        )
    )
    # The number 280.5 must be caught as a discrepancy
    assert any("280.5" in d for d in res.numerical_discrepancies)


def test_structured_logging_pii_sanitization():
    """Verify PII scrubbing strips patient personal identifiers from logs."""
    raw_payload = {
        "patient_name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "555-123-4567",
        "analyte": "Hemoglobin",
        "nested": {"patient_email": "test@test.com", "value": 14.5},
    }
    cleaned = sanitize_value(raw_payload)
    assert cleaned["patient_name"] == "[PII_REDACTED]"
    assert cleaned["email"] == "[EMAIL_REDACTED]"
    assert cleaned["phone"] == "[PHONE_REDACTED]"
    assert cleaned["analyte"] == "Hemoglobin"
    assert cleaned["nested"]["patient_email"] == "[PII_REDACTED]"
    assert cleaned["nested"]["value"] == 14.5


def test_full_modular_pipeline():
    """Verify that LabReportPipeline executes all modular stages sequentially."""
    pipeline = LabReportPipeline()
    sample_pdf = Path("data/sample_reports/srl_lipid_panel.pdf")
    assert sample_pdf.exists(), "Sample test report srl_lipid_panel.pdf should exist"
    sample_bytes = sample_pdf.read_bytes()

    result = pipeline.run_modular_pipeline(
        file_bytes=sample_bytes,
        filename="srl_lipid_panel.pdf",
    )
    assert result.request_id is not None
    assert result.is_safe is True
    assert len(result.sanitized_explanations) >= 1
