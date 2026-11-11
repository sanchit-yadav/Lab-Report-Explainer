"""Deterministic flagging engine for laboratory results.

Pure Python logic comparing observed analyte values against printed reference intervals.
Zero LLM reliance for 100% determinism, reproducibility, and auditability.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import FlaggingConfig, get_config
from src.extraction.schema import FlagStatus, LabReport, TestResult

logger = logging.getLogger("flagger")


class Flagger:
    """Classifies laboratory test results into clinical flag categories."""

    def __init__(self, config: Optional[FlaggingConfig] = None):
        if config is not None:
            self.config = config
        else:
            self.config = get_config().extraction.flagging

    def determine_flag(self, test: TestResult) -> FlagStatus:
        """Evaluate a single TestResult and determine its FlagStatus."""
        # ----------------------------------------------------------------------
        # Case 1: Non-numeric qualitative result (value is None)
        # ----------------------------------------------------------------------
        if test.value is None:
            raw_clean = test.raw_value.strip().lower()
            if not raw_clean:
                return FlagStatus.UNKNOWN

            # Check non_numeric_map from config (e.g. positive -> abnormal)
            if raw_clean in self.config.non_numeric_map:
                mapped = self.config.non_numeric_map[raw_clean]
                return FlagStatus.ABNORMAL if mapped == "abnormal" else FlagStatus.NORMAL

            # If raw_value matches ref_raw (e.g. "Negative" vs ref "Negative")
            ref_clean = test.ref_raw.strip().lower()
            if ref_clean and raw_clean == ref_clean:
                return FlagStatus.NORMAL

            # Unrecognized qualitative value
            return FlagStatus.UNKNOWN

        # ----------------------------------------------------------------------
        # Case 2: Numeric result
        # ----------------------------------------------------------------------
        val = test.value
        low = test.ref_low
        high = test.ref_high
        mult = self.config.critical_multiplier

        # Case 2A: Reference range is completely absent
        if low is None and high is None:
            return FlagStatus.UNKNOWN

        # Case 2B: Two-sided reference range [low, high]
        if low is not None and high is not None:
            span = high - low
            crit_high_cutoff = high + (span * mult)

            # If low - (span * mult) <= 0 (common for cell counts/concentrations bounded at 0),
            # apply proportional floor low / mult to ensure critical low is reachable
            if (low - (span * mult)) > 0:
                crit_low_cutoff = low - (span * mult)
            else:
                crit_low_cutoff = low / mult if low > 0 else low - (span * mult)

            if val >= crit_high_cutoff:
                return FlagStatus.CRITICAL_HIGH
            if val > high:
                return FlagStatus.HIGH
            if val <= crit_low_cutoff:
                return FlagStatus.CRITICAL_LOW
            if val < low:
                return FlagStatus.LOW
            return FlagStatus.NORMAL

        # Case 2C: Upper-bound only (e.g. Total Cholesterol < 200)
        if high is not None and low is None:
            crit_high_cutoff = high * mult if high > 0 else high + abs(high * mult)
            if val >= crit_high_cutoff:
                return FlagStatus.CRITICAL_HIGH
            if val > high:
                return FlagStatus.HIGH
            return FlagStatus.NORMAL

        # Case 2D: Lower-bound only (e.g. eGFR > 60 or HDL > 50)
        if low is not None and high is None:
            crit_low_cutoff = low / mult if low > 0 else low - abs(low * mult)
            if val <= crit_low_cutoff:
                return FlagStatus.CRITICAL_LOW
            if val < low:
                return FlagStatus.LOW
            return FlagStatus.NORMAL

        return FlagStatus.UNKNOWN

    def flag_test(self, test: TestResult) -> TestResult:
        """Assign flag to a TestResult instance in-place and return it."""
        test.flag = self.determine_flag(test)
        return test

    def flag_report(self, report: LabReport) -> LabReport:
        """Assign flags to all tests in a LabReport."""
        for test in report.tests:
            self.flag_test(test)
        return report
