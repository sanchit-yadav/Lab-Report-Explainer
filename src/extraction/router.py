"""Extraction Router orchestrating 3-tier fallback.

Attempts Tier 1 (pdfplumber) -> Tier 2 (camelot) -> Tier 3 (Gemini Vision).
Logs extraction provenance and tier transitions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Union

from src.config import get_config
from src.extraction.camelot_parser import CamelotExtractor
from src.extraction.pdf_parser import PDFPlumberExtractor
from src.extraction.schema import LabReport
from src.extraction.vision_parser import VisionExtractor, is_image_bytes

logger = logging.getLogger("extraction_router")


class ExtractionRouter:
    """Routes PDF reports through the 3-tier extraction hierarchy."""

    def __init__(self):
        self.config = get_config()
        self.tier1 = PDFPlumberExtractor()
        self.tier2 = CamelotExtractor()
        self.tier3 = VisionExtractor()

    def extract(self, pdf_source: Union[str, Path, bytes, BinaryIO]) -> LabReport:
        """Execute tiered extraction with automated fallback."""
        tiers = sorted(self.config.extraction.tiers, key=lambda t: t.priority)

        # Ensure we have bytes to allow re-reading if needed across tiers
        pdf_bytes: bytes
        if isinstance(pdf_source, (str, Path)):
            with open(pdf_source, "rb") as f:
                pdf_bytes = f.read()
        elif isinstance(pdf_source, bytes):
            pdf_bytes = pdf_source
        else:
            pdf_bytes = pdf_source.read()

        # Direct fast-path for image files (JPG, PNG, WebP)
        if is_image_bytes(pdf_bytes):
            logger.info(
                "Detected raw image format (JPEG/PNG/WebP). Routing directly to Tier 3 Vision OCR."
            )
            try:
                report = self.tier3.extract(pdf_bytes)
                if len(report.tests) > 0:
                    logger.info(f"Tier 3 (vision) extracted {len(report.tests)} tests from image.")
                    return report
                logger.warning("Tier 3 (vision) yielded 0 tests from image.")
            except Exception as e:
                logger.warning(f"Tier 3 vision failed on image with error: {e}")
            return LabReport(
                report_type="blood_test",
                tests=[],
                extraction_method="vision_image_failed",
            )

        for tier in tiers:
            if not tier.enabled:
                continue

            try:
                if tier.name == "pdfplumber":
                    report = self.tier1.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(
                            f"Tier 1 (pdfplumber) succeeded: extracted {len(report.tests)} tests."
                        )
                        return report
                    logger.warning(
                        "Tier 1 (pdfplumber) yielded 0 tests; attempting Tier 2 fallback."
                    )

                elif tier.name == "camelot":
                    # Fast check: Camelot only parses vector text streams and fails on image-based PDFs.
                    # If the document has no text layer, skip Camelot directly to Tier 3 Vision.
                    has_text = False
                    try:
                        import io

                        import pdfplumber

                        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                            has_text = any(
                                len((p.extract_text() or "").strip()) > 30 for p in pdf.pages
                            )
                    except Exception:
                        pass
                    if not has_text:
                        logger.info(
                            "PDF has no text layer; skipping Camelot directly to Tier 3 Vision OCR."
                        )
                        continue

                    report = self.tier2.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(
                            f"Tier 2 (camelot) succeeded: extracted {len(report.tests)} tests."
                        )
                        return report
                    logger.warning("Tier 2 (camelot) yielded 0 tests; attempting Tier 3 fallback.")

                elif tier.name == "vision":
                    report = self.tier3.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(
                            f"Tier 3 (vision) succeeded: extracted {len(report.tests)} tests."
                        )
                        return report
                    logger.warning("Tier 3 (vision) yielded 0 tests.")

            except Exception as e:
                logger.warning(f"Tier '{tier.name}' failed with error: {e}. Attempting next tier.")
                continue

        logger.error("All extraction tiers failed to extract test data.")
        return LabReport(
            report_type="blood_test",
            tests=[],
            extraction_method="failed",
        )
