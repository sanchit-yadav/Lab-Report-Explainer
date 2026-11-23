"""Biological plausibility and OCR degradation validation engine.

Ensures that implausible values (from line slippage, optical corruption, or scan blur)
trigger a safe re-upload request rather than risking inaccurate clinical hallucinations.
Rule: Low OCR confidence or implausible values -> ask for a better upload; NEVER guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("security.plausibility")

# Biological feasibility absolute bounds (values outside indicate optical/OCR corruption)
PHYSIOLOGICAL_BOUNDS = {
    "glucose": (10.0, 1500.0, "mg/dL"),
    "fasting blood glucose": (10.0, 1500.0, "mg/dL"),
    "hemoglobin": (1.5, 30.0, "g/dL"),
    "creatinine": (0.1, 35.0, "mg/dL"),
    "serum creatinine": (0.1, 35.0, "mg/dL"),
    "potassium": (1.0, 12.0, "mEq/L"),
    "sodium": (90.0, 190.0, "mEq/L"),
    "calcium": (2.0, 20.0, "mg/dL"),
    "total cholesterol": (20.0, 1200.0, "mg/dL"),
    "triglycerides": (10.0, 3000.0, "mg/dL"),
    "platelet": (1.0, 3000.0, "x10³/µL"),
    "platelet count": (1000.0, 3000000.0, "/uL"),
    "white blood cell": (100.0, 250000.0, "/uL"),
    "wbc": (0.1, 250.0, "x10³/µL"),
    "bun": (1.0, 250.0, "mg/dL"),
    "blood urea nitrogen": (1.0, 250.0, "mg/dL"),
    "alkaline phosphatase": (5.0, 3000.0, "U/L"),
    "alt": (1.0, 5000.0, "U/L"),
    "ast": (1.0, 5000.0, "U/L"),
    "tsh": (0.01, 250.0, "mIU/L"),
}


@dataclass
class PlausibilityResult:
    """Assessment of biological plausibility and OCR fidelity."""
    is_plausible: bool
    needs_better_upload: bool = False
    implausible_findings: List[str] = field(default_factory=list)
    advisory_message: str = ""


class PlausibilityValidator:
    """Verifies that all extracted measurements fall within physiologically possible boundaries."""

    def __init__(self, min_confidence_threshold: float = 0.40):
        self.min_confidence_threshold = min_confidence_threshold

    def validate_report(self, items: List[Any], avg_confidence: float = 1.0) -> PlausibilityResult:
        """Evaluate extracted biomarker items for physiological feasibility and scan confidence."""
        findings: List[str] = []

        # 1. OCR Confidence Floor
        if avg_confidence < self.min_confidence_threshold:
            findings.append(
                f"Overall document extraction confidence ({avg_confidence:.2f}) falls below minimum safety floor ({self.min_confidence_threshold:.2f})."
            )

        # 2. Analyte Bounds Verification
        for item in items:
            # Check individual analyte OCR confidence score
            conf = getattr(item, "confidence", 1.0)
            if conf is not None and conf < self.min_confidence_threshold:
                findings.append(
                    f"Low OCR confidence ({conf:.2f} < {self.min_confidence_threshold:.2f}) detected for analyte '{getattr(item, 'test_name', 'Analyte')}'. Visual character fidelity is degraded."
                )

            val = getattr(item, "value", None)
            if val is None:
                continue

            # Check strictly non-negative concentrations
            if val < 0.0:
                findings.append(f"Negative measurement detected for {getattr(item, 'test_name', 'Analyte')}: {val} (biologically impossible).")
                continue

            name_lower = getattr(item, "test_name", "").lower()
            for key, (b_low, b_high, unit) in PHYSIOLOGICAL_BOUNDS.items():
                if key in name_lower:
                    if val < b_low or val > b_high:
                        findings.append(
                            f"Implausible value for {item.test_name}: {val} (expected physiological limits: {b_low} to {b_high} {unit})."
                        )
                    break

        if findings:
            advisory = (
                "⚠️ **Upload Quality Notice:** One or more extracted laboratory values appear biologically implausible "
                "or corrupted due to scan quality/distortion. Rather than guessing, please upload a clearer, "
                "higher-resolution, or flatter image of your report to ensure accurate medical education."
            )
            return PlausibilityResult(
                is_plausible=False,
                needs_better_upload=True,
                implausible_findings=findings,
                advisory_message=advisory,
            )

        return PlausibilityResult(is_plausible=True, needs_better_upload=False)
