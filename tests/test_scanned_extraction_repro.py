"""Test verification for scanned report extraction and rasterization.

Verifies the resolution of the bug: 'can't extract anything from scanned reports'.
Confirms that:
1. Scanned / image-only PDFs rasterize at ~300 DPI, eliminating raw PDF bytecode leakage
   and cleanly extracting clinical parameters.
2. Multi-page image-only PDFs extract all pages correctly.
3. Extracted output satisfies schema validation:
   {test_name, value, unit, ref_low, ref_high, flag, source_page, source_location, confidence}.
4. Flags are computed deterministically in pure code from printed reference ranges.
"""

from pathlib import Path

from src.extraction.schema import FlagStatus
from src.stages.extract import ExtractValuesStage
from src.stages.ocr import OCRParseStage
from src.stages.schemas import ExtractValuesInput, OCRParseInput


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "scanned"


def test_scanned_pdf_rasterization_fixes_raw_binary_leak():
    """Confirms that OCRParseStage rasterizes scanned PDFs and extracts clean text without %PDF- leaks."""
    pdf_path = FIXTURES_DIR / "scanned_clean.pdf"
    assert pdf_path.exists(), "Synthetic scanned PDF fixture must exist"

    file_bytes = pdf_path.read_bytes()
    stage = OCRParseStage()
    parsed = stage.parse(OCRParseInput(file_bytes=file_bytes, filename="scanned_clean.pdf"))

    # Verify no raw bytecode leakage
    assert "%PDF-" not in parsed.full_text, "Raw binary bytecode must not leak into OCR text output!"
    # Verify clinical parameters extracted
    assert "Hemoglobin" in parsed.full_text
    assert "Platelets" in parsed.full_text
    assert parsed.confidence >= 0.70
    assert parsed.needs_clearer_image is False


def test_scanned_multipage_pdf_extracts_both_pages():
    """Confirms that multi-page image-only PDFs rasterize and parse both pages."""
    pdf_path = FIXTURES_DIR / "scanned_multipage.pdf"
    assert pdf_path.exists(), "Multi-page synthetic scanned PDF fixture must exist"

    file_bytes = pdf_path.read_bytes()
    stage = OCRParseStage()
    parsed = stage.parse(OCRParseInput(file_bytes=file_bytes, filename="scanned_multipage.pdf"))

    assert parsed.total_pages == 2
    assert len(parsed.pages) == 2
    # Verify Page 1 parameter and Page 2 parameter are present
    assert "Hemoglobin" in parsed.full_text
    assert "Serum Calcium" in parsed.full_text


def test_scanned_extraction_schema_validation_and_deterministic_flags():
    """Confirms that extracted output conforms to strict schema and computes deterministic flags."""
    pdf_path = FIXTURES_DIR / "scanned_clean.pdf"
    file_bytes = pdf_path.read_bytes()

    stage_ocr = OCRParseStage()
    stage_extract = ExtractValuesStage()

    parsed = stage_ocr.parse(OCRParseInput(file_bytes=file_bytes, filename="scanned_clean.pdf"))
    ext_out = stage_extract.extract(ExtractValuesInput(parsed_doc=parsed, raw_bytes=file_bytes))

    assert len(ext_out.items) == 4, f"Expected 4 tests, got {len(ext_out.items)}"

    tests_by_name = {item.test_name.lower(): item for item in ext_out.items}

    # Hemoglobin: 14.2 g/dL, ref 13.0 - 17.0 -> NORMAL
    hb = tests_by_name.get("hemoglobin")
    assert hb is not None
    assert hb.value == 14.2
    assert "g/dl" in hb.unit.lower()
    assert hb.ref_low == 13.0
    assert hb.ref_high == 17.0
    assert hb.flag == FlagStatus.NORMAL
    assert hb.source_page == 1
    assert hb.source_location is not None
    assert hb.confidence >= 0.80

    # White Blood Cell Count: 11.5, ref 4.0 - 10.0 -> HIGH
    wbc_key = next((k for k in tests_by_name if "white" in k or "wbc" in k), None)
    assert wbc_key is not None
    wbc = tests_by_name[wbc_key]
    assert wbc.value == 11.5
    assert wbc.flag == FlagStatus.HIGH

    # Platelets: 130.0, ref 150.0 - 450.0 -> LOW
    plt = tests_by_name.get("platelets")
    assert plt is not None
    assert plt.value == 130.0
    assert plt.flag == FlagStatus.LOW

    # Glucose: 105.0, ref 70.0 - 99.0 -> HIGH
    glu_key = next((k for k in tests_by_name if "glucose" in k), None)
    assert glu_key is not None
    glu = tests_by_name[glu_key]
    assert glu.value == 105.0
    assert glu.flag == FlagStatus.HIGH
