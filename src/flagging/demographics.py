"""Clinical Multi-Demographic Reference Interval Stratification Matrix.

Adjusts laboratory reference intervals dynamically based on patient biological sex,
pediatric vs geriatric age brackets, and physiological states (e.g. pediatric bone growth ALP).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from src.extraction.loinc_mapper import LOINCMapper
from src.extraction.schema import LabReport, TestResult

logger = logging.getLogger("flagging.demographics")


@dataclass
class DemographicContext:
    """Parsed patient demographic context for clinical interval stratification."""

    age_years: Optional[float] = None
    sex: Optional[str] = None  # "M", "F", or None
    is_pediatric: bool = False
    is_geriatric: bool = False


# Canonical Stratified Reference Ranges: (age_min, age_max, sex) -> (ref_low, ref_high)
DEMOGRAPHIC_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    # Hemoglobin (g/dL) - LOINC 718-7
    "718-7": {
        "infant": (10.0, 14.0),
        "child": (11.5, 15.5),
        "adult_male": (13.5, 17.5),
        "adult_female": (12.0, 15.5),
        "default": (12.0, 17.0),
    },
    # Serum Creatinine (mg/dL) - LOINC 2160-0
    "2160-0": {
        "child": (0.3, 0.7),
        "adult_male": (0.7, 1.3),
        "adult_female": (0.6, 1.1),
        "default": (0.6, 1.2),
    },
    # Serum Ferritin (ng/mL) - LOINC 2276-4
    "2276-4": {
        "child": (10.0, 140.0),
        "adult_male": (24.0, 336.0),
        "adult_female": (11.0, 307.0),
        "default": (20.0, 250.0),
    },
    # Uric Acid (mg/dL) - LOINC 3084-1
    "3084-1": {
        "adult_male": (3.4, 7.0),
        "adult_female": (2.4, 6.0),
        "default": (3.0, 7.0),
    },
    # Alkaline Phosphatase (U/L) - LOINC 6768-6
    # Note: Pediatric bone growth causes physiological ALP elevations up to 390 U/L
    "6768-6": {
        "child": (93.0, 390.0),
        "adult": (44.0, 147.0),
        "default": (44.0, 147.0),
    },
    # HDL Cholesterol (mg/dL) - LOINC 2085-9
    "2085-9": {
        "adult_male": (40.0, 999.0),
        "adult_female": (50.0, 999.0),
        "default": (40.0, 999.0),
    },
}


class DemographicIntervalEngine:
    """Evaluates demographic clinical intervals for age- and sex-stratified accuracy."""

    @classmethod
    def parse_demographics(
        cls,
        age_str: Optional[str],
        gender_str: Optional[str],
    ) -> DemographicContext:
        """Extract clean numeric age in years and canonical sex (M/F) from metadata."""
        age_years: Optional[float] = None
        if age_str:
            # Match formats like '45 Y', '45', '6 Months', '14 Days'
            nums = re.findall(r"\d+(?:\.\d+)?", str(age_str))
            if nums:
                val = float(nums[0])
                low = str(age_str).lower()
                if "m" in low and ("month" in low or "mo" in low):
                    age_years = val / 12.0
                elif "d" in low and ("day" in low or "d" in low):
                    age_years = val / 365.0
                else:
                    age_years = val

        sex: Optional[str] = None
        if gender_str:
            g_low = str(gender_str).strip().lower()
            if g_low.startswith("f") or "female" in g_low or "महिला" in g_low:
                sex = "F"
            elif g_low.startswith("m") or "male" in g_low or "पुरुष" in g_low:
                sex = "M"

        is_ped = age_years is not None and age_years < 18.0
        is_ger = age_years is not None and age_years >= 65.0

        return DemographicContext(
            age_years=age_years,
            sex=sex,
            is_pediatric=is_ped,
            is_geriatric=is_ger,
        )

    @classmethod
    def resolve_bracket(cls, loinc_code: str, demo: DemographicContext) -> str:
        """Select the appropriate demographic cohort key for a given LOINC test."""
        if loinc_code not in DEMOGRAPHIC_RANGES:
            return "default"

        available = DEMOGRAPHIC_RANGES[loinc_code]

        # 1. Pediatric check
        if demo.age_years is not None:
            if demo.age_years < 1.0 and "infant" in available:
                return "infant"
            if demo.age_years < 18.0 and "child" in available:
                return "child"

        # 2. Sex specific check
        if demo.sex == "M" and "adult_male" in available:
            return "adult_male"
        if demo.sex == "F" and "adult_female" in available:
            return "adult_female"

        # 3. Adult general
        if "adult" in available and (demo.age_years is None or demo.age_years >= 18.0):
            return "adult"

        return "default"

    @classmethod
    def refine_analyte_range(
        cls,
        test: TestResult,
        demo: DemographicContext,
    ) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Determine if demographic stratification refines the reference interval."""
        if not test.loinc_code:
            LOINCMapper.enrich_test_result(test)

        if not test.loinc_code or test.loinc_code not in DEMOGRAPHIC_RANGES:
            return test.ref_low, test.ref_high, None

        bracket = cls.resolve_bracket(test.loinc_code, demo)
        ref_low, ref_high = DEMOGRAPHIC_RANGES[test.loinc_code][bracket]

        note: Optional[str] = None
        # If report had no reference range, adopt demographic range directly
        if test.ref_low is None and test.ref_high is None:
            note = f"Demographic reference interval applied ({bracket.replace('_', ' ')})"
            return ref_low, ref_high if ref_high < 900.0 else None, note

        # Special clinical case: Pediatric Alkaline Phosphatase
        # Labs often print adult ALP ranges (44-147) on child reports, falsely flagging them as abnormal
        if test.loinc_code == "6768-6" and demo.is_pediatric and bracket == "child":
            note = "Pediatric bone-growth interval applied (44-390 U/L)"
            return ref_low, ref_high, note

        return test.ref_low, test.ref_high, None

    @classmethod
    def apply_demographic_stratification(cls, report: LabReport) -> LabReport:
        """Apply demographic interval intelligence across all analytes in a report."""
        demo = cls.parse_demographics(report.patient_age, report.patient_gender)

        for test in report.tests:
            low, high, note = cls.refine_analyte_range(test, demo)
            if note:
                test.ref_low = low
                test.ref_high = high
                test.ref_raw = (
                    f"{low} - {high}" if low is not None and high is not None else test.ref_raw
                )
                logger.info(f"Refined {test.test_name} for patient demographic: {note}")

        return report
