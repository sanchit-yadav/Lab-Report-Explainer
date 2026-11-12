"""Tier 3 Vision Extractor using Gemini 3.5 Flash.

Fallback for scanned image PDFs, non-searchable documents, or degraded reports.
Renders PDF pages to images via pypdfium2 and uses Gemini multimodal vision
with structured schema output.
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
import re
from typing import BinaryIO, List, Optional, Union

import pypdfium2 as pdfium
from google import genai
from google.genai import types

from src.config import get_config
from src.extraction.schema import LabReport, TestResult

logger = logging.getLogger("vision_parser")


VISION_EXTRACTION_PROMPT = """
You are a precise clinical document digitization assistant.
Analyze the provided medical laboratory report page image.
Extract all laboratory test parameters, values, units, and reference intervals into a structured format.

For each test row:
- test_name: Exact analyte / investigation name
- raw_value: Original value string printed on report (e.g. '14.2', '< 0.5', 'Positive')
- value: Numeric float representation of raw_value, or null if non-numeric
- unit: Measurement unit (e.g. 'g/dL', 'mg/dL', 'cells/cumm')
- ref_raw: Original reference interval string (e.g. '13.0 - 17.0', '< 200', '> 60')
- ref_low: Float lower bound, or null if one-sided or not given
- ref_high: Float upper bound, or null if one-sided or not given

Also extract patient_name, patient_age, patient_gender, report_date, and lab_name if visible.
"""


def is_image_bytes(data: bytes) -> bool:
    """Check if byte sequence starts with known image file signatures."""
    if len(data) < 4:
        return False
    return (
        data.startswith(b"\xff\xd8\xff")  # JPEG
        or data.startswith(b"\x89PNG")    # PNG
        or (data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP")  # WebP
    )


def detect_mime_type(data: bytes) -> str:
    """Identify image MIME type based on header magic bytes."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class VisionExtractor:
    """Extracts lab reports from image files or scanned PDFs using Gemini 3.5 Flash."""

    def __init__(self):
        self.tier_id = 3
        self.config = get_config()

    def extract(self, source: Union[str, Path, bytes, BinaryIO]) -> LabReport:
        """Extract structured data from image files or rendered PDF pages."""
        api_key = self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Tier 3 Vision fallback requires a valid Gemini API key."
            )

        # 1. Resolve raw bytes
        raw_bytes: bytes
        if isinstance(source, (str, Path)):
            with open(source, "rb") as f:
                raw_bytes = f.read()
        elif isinstance(source, bytes):
            raw_bytes = source
        else:
            raw_bytes = source.read()

        images_data: List[tuple[bytes, str]] = []
        is_direct_image = is_image_bytes(raw_bytes)

        if is_direct_image:
            # Directly provided image (JPEG, PNG, WebP)
            mime = detect_mime_type(raw_bytes)
            images_data.append((raw_bytes, mime))
        else:
            # Render PDF page(s) to image bytes using pypdfium2
            pdf = pdfium.PdfDocument(raw_bytes)
            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                pil_image = page.render(scale=2.0).to_pil()
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format="JPEG", quality=90)
                images_data.append((img_byte_arr.getvalue(), "image/jpeg"))

        client = genai.Client(api_key=api_key)
        all_tests: List[TestResult] = []
        patient_name = None
        lab_name = None

        # Process each image page with Gemini 3.5 Flash
        for img_bytes, mime_type in images_data:
            content_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)

            response = client.models.generate_content(
                model=self.config.models.vision_fallback,
                contents=[content_part, VISION_EXTRACTION_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LabReport,
                    temperature=0.0,
                ),
            )

            if response.text:
                clean_text = response.text.strip()
                if clean_text.startswith("```"):
                    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                    clean_text = re.sub(r"\s*```$", "", clean_text)
                try:
                    parsed_dict = json.loads(clean_text)
                except Exception as e:
                    logger.warning(f"Failed to parse vision response JSON on a page: {e}")
                    continue

                if not patient_name and parsed_dict.get("patient_name"):
                    patient_name = parsed_dict.get("patient_name")
                if not lab_name and parsed_dict.get("lab_name"):
                    lab_name = parsed_dict.get("lab_name")

                for t in parsed_dict.get("tests", []):
                    all_tests.append(
                        TestResult(
                            test_name=t.get("test_name", ""),
                            value=t.get("value"),
                            raw_value=t.get("raw_value", ""),
                            unit=t.get("unit", ""),
                            ref_low=t.get("ref_low"),
                            ref_high=t.get("ref_high"),
                            ref_raw=t.get("ref_raw", ""),
                            extraction_tier=self.tier_id,
                        )
                    )

        return LabReport(
            patient_name=patient_name,
            lab_name=lab_name,
            report_type="blood_test",
            tests=all_tests,
            extraction_method="vision",
        )
