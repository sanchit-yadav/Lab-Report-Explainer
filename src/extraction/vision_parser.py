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
import re
from pathlib import Path
from typing import BinaryIO, List, Union

import pypdfium2 as pdfium
from google import genai
from google.genai import types
from PIL import Image

from src.config import available_models, get_config, mark_model_cooldown, record_llm_usage
from src.extraction.preprocessing import DocumentPreprocessor
from src.extraction.schema import LabReport, TestResult
from src.flagging.flagger import Flagger

logger = logging.getLogger("vision_parser")


VISION_EXTRACTION_PROMPT = """
You are an expert clinical laboratory document digitization system.
Analyze the provided medical laboratory report image with maximum precision.
Extract ALL laboratory test rows, biomarker names, patient results, units, and reference ranges into structured JSON.

For each test row:
- test_name: Full standard name of the analyte/test (e.g., 'Hemoglobin', 'Total Cholesterol', 'Platelet Count')
- raw_value: Exact printed result string (e.g. '14.2', '< 0.5', '150,000', 'Negative')
- value: Numeric float value of the result, or null if non-numeric/sentinel (e.g. 150000.0 for 150,000; 14.2 for 14.2)
- unit: Measurement unit (e.g. 'g/dL', 'mg/dL', '10^3/uL', 'mmol/L', 'uIU/mL', '%')
- ref_raw: Exact printed reference interval string (e.g. '13.0 - 17.0', '< 200', '150,000 - 450,000')
- ref_low: Float lower bound, or null if single-sided upper bound (< X)
- ref_high: Float upper bound, or null if single-sided lower bound (> X)
- source_location: Spatial or row position (e.g. 'Row 3')
- confidence: Number between 0.0 and 1.0 indicating clarity

Also extract patient_name, patient_age, patient_gender, report_date, and lab_name if visible.
Never invent or hallucinate test names, values, or reference ranges. If no tests exist on this page, return an empty tests list.
"""


def is_image_bytes(data: bytes) -> bool:
    """Check if byte sequence starts with known image file signatures."""
    if len(data) < 4:
        return False
    return (
        data.startswith(b"\xff\xd8\xff")  # JPEG
        or data.startswith(b"\x89PNG")  # PNG
        or (data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP")  # WebP
        or data.startswith(b"MM\x00*")  # TIFF big-endian
        or data.startswith(b"II*\x00")  # TIFF little-endian
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
        return genai.Client(
            api_key=api_key, http_options={"api_version": "v1beta", "timeout": 20000}
        )

    def _call_model_with_fallback(
        self,
        client: genai.Client,
        content_part: types.Part,
        prompt: str,
    ) -> str:
        """Call primary vision model with automatic fallback and cooldown circuit-breaking."""
        models_to_try = [
            getattr(self.config.models, "vision_fallback", "gemini-3.5-flash-lite"),
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
        ]
        # Deduplicate while preserving priority order, skipping models in active cooldown
        seen = set()
        deduped_models = available_models(
            [m for m in models_to_try if m and not (m in seen or seen.add(m))]
        )

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
                    record_llm_usage(model_name, response)
                    return response.text.strip()
            except Exception as e:
                err_str = str(e)
                mark_model_cooldown(model_name, err_str)
                logger.warning(
                    f"Vision model '{model_name}' encountered error: {e}. Trying next model."
                )
                last_err = e

        raise RuntimeError(f"All vision models failed. Last error: {last_err}")

    def extract_from_image(
        self, pil_image: Image.Image, page_idx: int = 1, preprocessed: bool = False
    ) -> LabReport:
        """Preprocess and extract laboratory parameters from a single PIL image."""
        # Step 0: Downscale oversized images before running heavy CV filtering (cap max dimension at 1800px)
        max_dim = max(pil_image.size)
        if max_dim > 1800:
            scale_factor = 1800.0 / max_dim
            new_size = (int(pil_image.width * scale_factor), int(pil_image.height * scale_factor))
            pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)

        # Step 1: Preprocess (orientation fix, deskew, noise reduction, contrast normalization) if not already done
        if not preprocessed:
            clean_img, meta = self.preprocessor.preprocess(pil_image)
        else:
            clean_img = pil_image

        # Step 2: Encode to JPEG at quality 85 for rapid network transport
        img_byte_arr = io.BytesIO()
        clean_img.save(img_byte_arr, format="JPEG", quality=85)
        raw_bytes = img_byte_arr.getvalue()

        client = self._get_genai_client()
        content_part = types.Part.from_bytes(data=raw_bytes, mime_type="image/jpeg")

        raw_response_text = self._call_model_with_fallback(
            client, content_part, VISION_EXTRACTION_PROMPT
        )

        clean_text = raw_response_text
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        parsed_dict = json.loads(clean_text)

        from src.extraction.normalizer import parse_numeric_value, parse_reference_range

        all_tests: List[TestResult] = []
        for t in parsed_dict.get("tests", []):
            val = t.get("value")
            raw_val = str(t.get("raw_value") or "").strip()
            # Robust normalization: handles commas (150,000), sentinels (Negative), inequalities (< 0.5)
            if val is None and raw_val:
                val = parse_numeric_value(raw_val)

            ref_low = t.get("ref_low")
            ref_high = t.get("ref_high")
            ref_raw = str(t.get("ref_raw") or "").strip()
            # Robust reference boundaries: handles commas (150,000 - 450,000), single-sided (< 200, > 60)
            if (ref_low is None or ref_high is None) and ref_raw:
                p_low, p_high = parse_reference_range(ref_raw)
                if ref_low is None:
                    ref_low = p_low
                if ref_high is None:
                    ref_high = p_high

            test_obj = TestResult(
                test_name=t.get("test_name", ""),
                value=val,
                raw_value=raw_val or (str(val) if val is not None else ""),
                unit=t.get("unit", "") or "",
                ref_low=ref_low,
                ref_high=ref_high,
                ref_raw=ref_raw,
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
            # Render PDF pages at ~180 DPI (scale=2.5) for optimal OCR speed and memory
            pdf = pdfium.PdfDocument(raw_bytes)
            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                pil_image = page.render(scale=180.0 / 72.0).to_pil()
                pil_pages.append(pil_image)

        all_tests: List[TestResult] = []
        patient_name = None
        lab_name = None

        if len(pil_pages) <= 1:
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
        else:
            from concurrent.futures import ThreadPoolExecutor

            def _proc(item):
                p_idx, p_img = item
                try:
                    return self.extract_from_image(p_img, page_idx=p_idx)
                except Exception as e:
                    logger.warning(f"Error extracting parameters on page {p_idx}: {e}")
                    return None

            with ThreadPoolExecutor(max_workers=min(4, len(pil_pages))) as executor:
                reports = list(executor.map(_proc, enumerate(pil_pages, start=1)))

            for rep in reports:
                if rep:
                    if not patient_name and rep.patient_name:
                        patient_name = rep.patient_name
                    if not lab_name and rep.lab_name:
                        lab_name = rep.lab_name
                    all_tests.extend(rep.tests)

        return LabReport(
            patient_name=patient_name,
            lab_name=lab_name,
            report_type="blood_test",
            tests=all_tests,
            extraction_method="vision",
        )
