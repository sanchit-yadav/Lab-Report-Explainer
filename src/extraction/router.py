"""Extraction Router orchestrating 3-tier fallback.

Attempts Tier 1 (pdfplumber) -> Tier 2 (camelot) -> Tier 3 (Gemini Vision).
Logs extraction provenance and tier transitions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Optional, Union

from src.config import get_config
from src.extraction.camelot_parser import CamelotExtractor
from src.extraction.pdf_parser import PDFPlumberExtractor
from src.extraction.schema import LabReport
from src.extraction.vision_parser import VisionExtractor

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

        for tier in tiers:
            if not tier.enabled:
                continue

            try:
                if tier.name == "pdfplumber":
                    report = self.tier1.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(f"Tier 1 (pdfplumber) succeeded: extracted {len(report.tests)} tests.")
                        return report
                    logger.warning("Tier 1 (pdfplumber) yielded 0 tests; attempting Tier 2 fallback.")

                elif tier.name == "camelot":
                    report = self.tier2.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(f"Tier 2 (camelot) succeeded: extracted {len(report.tests)} tests.")
                        return report
                    logger.warning("Tier 2 (camelot) yielded 0 tests; attempting Tier 3 fallback.")

                elif tier.name == "vision":
                    report = self.tier3.extract(pdf_bytes)
                    if len(report.tests) > 0:
                        logger.info(f"Tier 3 (vision) succeeded: extracted {len(report.tests)} tests.")
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
