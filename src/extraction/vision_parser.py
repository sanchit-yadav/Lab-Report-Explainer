"""Tier 3 Multimodal Vision Extractor using Gemini Flash.

Fallback for scanned image PDFs, non-searchable documents, or degraded reports.
Renders PDF pages to images via pypdfium2 at ~300 DPI, runs robust preprocessing
(orientation fix, deskew, contrast normalization), and performs multimodal
information extraction with structured schema output.
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
import re
from typing import BinaryIO, List, Optional, Union

from PIL import Image
import pypdfium2 as pdfium
from google import genai
from google.genai import types

from src.config import get_config
from src.extraction.schema import LabReport, TestResult
from src.flagging.flagger import Flagger
from src.extraction.preprocessing import DocumentPreprocessor

logger = logging.getLogger("vision_parser")


VISION_EXTRACTION_PROMPT = """
You are a precise clinical document digitization assistant.
Analyze the provided medical laboratory report page image.
Extract all laboratory test parameters, values, units, and reference intervals into a structured format.

For each test row:
- test_name: Exact analyte / investigation name (e.g. 'Hemoglobin', 'Serum Creatinine', 'TSH')
- raw_value: Original value string printed on report (e.g. '14.2', '< 0.5', 'Positive')
- value: Numeric float representation of raw_value, or null if non-numeric
- unit: Measurement unit (e.g. 'g/dL', 'mg/dL', '10^3/uL', 'mmol/L', 'uIU/mL')
- ref_raw: Original reference interval string (e.g. '13.0 - 17.0', '< 200', '> 60')
- ref_low: Float lower bound, or null if one-sided or not given
- ref_high: Float upper bound, or null if one-sided or not given
- source_location: Spatial or row position (e.g. 'Row 1, Column 2', 'Table 1 Line 3')
- confidence: Character clarity confidence between 0.0 (unreadable blur) and 1.0 (crystal clear text)

Also extract patient_name, patient_age, patient_gender, report_date, and lab_name if visible.
Never invent or hallucinate test names, values, or reference ranges. If no tests exist on this page, return an empty tests list.
"""


def is_image_bytes(data: bytes) -> bool:
    """Check if byte sequence starts with known image file signatures."""
    if len(data) < 4:
        return False
    return (
        data.startswith(b"\xff\xd8\xff")  # JPEG
        or data.startswith(b"\x89PNG")    # PNG
        or (data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP")  # WebP
        or data.startswith(b"MM\x00*")    # TIFF big-endian
        or data.startswith(b"II*\x00")    # TIFF little-endian
    )


def detect_mime_type(data: bytes) -> str:
    """Identify image MIME type based on header magic bytes."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class VisionExtractor:
    """Extracts lab reports from image files or scanned PDFs using Gemini Flash."""

    def __init__(self):
        self.tier_id = 3
        self.config = get_config()
        self.preprocessor = DocumentPreprocessor()
        self.flagger = Flagger(self.config.extraction.flagging)

    def _get_genai_client(self) -> genai.Client:
        """Instantiate Google GenAI client configured with v1beta endpoint for JSON schema support."""
        api_key = self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Multimodal Vision fallback requires a valid Gemini API key."
            )
        return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    def _call_model_with_fallback(
        self,
        client: genai.Client,
        content_part: types.Part,
        prompt: str,
    ) -> str:
        """Call primary vision model with automatic fallback to secondary models if unavailable."""
        models_to_try = [
            getattr(self.config.models, "vision_fallback", "gemini-2.5-flash"),
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        # Deduplicate while preserving priority order
        seen = set()
        deduped_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

        last_err = None
        for model_name in deduped_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[content_part, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=LabReport,
                        temperature=0.0,
                    ),
                )
                if response.text:
                    return response.text.strip()
            except Exception as e:
                logger.warning(f"Vision model '{model_name}' encountered error: {e}. Trying next model.")
                last_err = e

        raise RuntimeError(f"All vision models failed. Last error: {last_err}")

    def extract_from_image(self, pil_image: Image.Image, page_idx: int = 1) -> LabReport:
        """Preprocess and extract laboratory parameters from a single PIL image."""
        # Step 1: Preprocess (orientation fix, deskew, noise reduction, contrast normalization)
        clean_img, meta = self.preprocessor.preprocess(pil_image)

        # Step 2: Encode to high-quality JPEG
        img_byte_arr = io.BytesIO()
        clean_img.save(img_byte_arr, format="JPEG", quality=95)
        raw_bytes = img_byte_arr.getvalue()

        client = self._get_genai_client()
        content_part = types.Part.from_bytes(data=raw_bytes, mime_type="image/jpeg")

        raw_response_text = self._call_model_with_fallback(client, content_part, VISION_EXTRACTION_PROMPT)

        clean_text = raw_response_text
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        parsed_dict = json.loads(clean_text)

        all_tests: List[TestResult] = []
        for t in parsed_dict.get("tests", []):
            test_obj = TestResult(
                test_name=t.get("test_name", ""),
                value=t.get("value"),
                raw_value=t.get("raw_value", "") or (str(t.get("value")) if t.get("value") is not None else ""),
                unit=t.get("unit", "") or "",
                ref_low=t.get("ref_low"),
                ref_high=t.get("ref_high"),
                ref_raw=t.get("ref_raw", ""),
                source_page=page_idx,
                source_location=t.get("source_location") or f"Page {page_idx}",
                confidence=float(t.get("confidence", 0.95)),
                extraction_tier=self.tier_id,
            )
            # Guarantee deterministic reference range flagging in pure Python code
            test_obj.flag = self.flagger.determine_flag(test_obj)
            all_tests.append(test_obj)

        return LabReport(
            patient_name=parsed_dict.get("patient_name"),
            lab_name=parsed_dict.get("lab_name"),
            report_type="blood_test",
            tests=all_tests,
            extraction_method="vision",
        )

    def extract(self, source: Union[str, Path, bytes, BinaryIO]) -> LabReport:
        """Extract structured data from image files or rendered PDF pages."""
        # 1. Resolve raw bytes
        raw_bytes: bytes
        if isinstance(source, (str, Path)):
            with open(source, "rb") as f:
                raw_bytes = f.read()
        elif isinstance(source, bytes):
            raw_bytes = source
        else:
            raw_bytes = source.read()

        is_direct_image = is_image_bytes(raw_bytes)
        pil_pages: List[Image.Image] = []

        if is_direct_image:
            pil_pages.append(Image.open(io.BytesIO(raw_bytes)))
        else:
            # Render PDF pages to images at ~300 DPI (scale=4.1667) using pypdfium2
            pdf = pdfium.PdfDocument(raw_bytes)
            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                pil_image = page.render(scale=300.0 / 72.0).to_pil()
                pil_pages.append(pil_image)

        all_tests: List[TestResult] = []
        patient_name = None
        lab_name = None

        for page_idx, page_img in enumerate(pil_pages, start=1):
            try:
                page_report = self.extract_from_image(page_img, page_idx=page_idx)
                if not patient_name and page_report.patient_name:
                    patient_name = page_report.patient_name
                if not lab_name and page_report.lab_name:
                    lab_name = page_report.lab_name
                all_tests.extend(page_report.tests)
            except Exception as e:
                logger.warning(f"Error extracting parameters on page {page_idx}: {e}")

        return LabReport(
            patient_name=patient_name,
            lab_name=lab_name,
            report_type="blood_test",
            tests=all_tests,
            extraction_method="vision",
        )
