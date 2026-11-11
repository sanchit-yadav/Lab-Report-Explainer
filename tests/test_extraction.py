"""Unit and integration tests for PDF Extraction components."""

from pathlib import Path
import pytest

from src.extraction.pdf_parser import PDFPlumberExtractor
from src.extraction.router import ExtractionRouter
from src.extraction.schema import LabReport

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_reports"


def test_pdfplumber_extracts_thyrocare_cbc():
    pdf_path = SAMPLE_DIR / "thyrocare_cbc.pdf"
    assert pdf_path.exists(), "Sample PDF not found"

    extractor = PDFPlumberExtractor()
    report = extractor.extract(pdf_path)

    assert isinstance(report, LabReport)
    assert len(report.tests) == 8
    assert report.patient_name == "Aarav Sharma"
    assert report.extraction_method == "pdfplumber"

    test_names = [t.test_name for t in report.tests]
    assert "Hemoglobin" in test_names
    assert "WBC Count" in test_names
    assert "Platelet Count" in test_names

    hb = next(t for t in report.tests if t.test_name == "Hemoglobin")
    assert hb.value == 14.2
    assert hb.unit == "g/dL"
    assert hb.ref_low == 13.0
    assert hb.ref_high == 17.0


def test_router_multipage_full_body():
    pdf_path = SAMPLE_DIR / "multipage_full_body.pdf"
    assert pdf_path.exists()

    router = ExtractionRouter()
    report = router.extract(pdf_path)

    assert isinstance(report, LabReport)
    # Multipage report should aggregate tests across pages
    assert len(report.tests) >= 12
    assert report.patient_name == "Meera Iyer"


def test_router_non_numeric_report():
    pdf_path = SAMPLE_DIR / "non_numeric.pdf"
    assert pdf_path.exists()

    router = ExtractionRouter()
    report = router.extract(pdf_path)

    assert isinstance(report, LabReport)
    assert len(report.tests) >= 6
    protein = next((t for t in report.tests if "protein" in t.test_name.lower()), None)
    assert protein is not None
    assert protein.value is None
    assert protein.raw_value.lower() == "trace"
