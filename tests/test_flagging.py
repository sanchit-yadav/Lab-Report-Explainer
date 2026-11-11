"""Comprehensive unit tests for the deterministic Flagger engine.

Tests all boundary conditions, critical multipliers, one-sided ranges,
non-numeric qualitative findings, and edge cases.
"""

import pytest
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.flagging.flagger import Flagger


@pytest.fixture
def flagger():
    return Flagger()


# ------------------------------------------------------------------------------
# 1. Two-Sided Reference Range Tests [low, high]
# ------------------------------------------------------------------------------

def test_two_sided_normal_values(flagger):
    # Hemoglobin range: 13.0 to 17.0 (span = 4.0, crit_high = 25.0, crit_low = 5.0)
    t = TestResult(test_name="Hemoglobin", value=15.0, raw_value="15.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t) == FlagStatus.NORMAL


def test_two_sided_exact_boundaries(flagger):
    # Exact lower limit should be NORMAL (inclusive boundary)
    t_low = TestResult(test_name="Hemoglobin", value=13.0, raw_value="13.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_low) == FlagStatus.NORMAL

    # Exact upper limit should be NORMAL (inclusive boundary)
    t_high = TestResult(test_name="Hemoglobin", value=17.0, raw_value="17.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_high) == FlagStatus.NORMAL


def test_two_sided_high_and_critical_high(flagger):
    # Range 13.0 - 17.0 (span = 4.0; crit_high = 17.0 + 4.0 * 2.0 = 25.0)
    t_high = TestResult(test_name="Hemoglobin", value=18.5, raw_value="18.5", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_high) == FlagStatus.HIGH

    t_crit = TestResult(test_name="Hemoglobin", value=26.0, raw_value="26.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_crit) == FlagStatus.CRITICAL_HIGH

    # Boundary for critical high
    t_crit_exact = TestResult(test_name="Hemoglobin", value=25.0, raw_value="25.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_crit_exact) == FlagStatus.CRITICAL_HIGH


def test_two_sided_low_and_critical_low(flagger):
    # Range 13.0 - 17.0 (span = 4.0; crit_low = 13.0 - 4.0 * 2.0 = 5.0)
    t_low = TestResult(test_name="Hemoglobin", value=11.2, raw_value="11.2", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_low) == FlagStatus.LOW

    t_crit = TestResult(test_name="Hemoglobin", value=4.5, raw_value="4.5", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_crit) == FlagStatus.CRITICAL_LOW

    # Boundary for critical low
    t_crit_exact = TestResult(test_name="Hemoglobin", value=5.0, raw_value="5.0", ref_low=13.0, ref_high=17.0)
    assert flagger.determine_flag(t_crit_exact) == FlagStatus.CRITICAL_LOW


# ------------------------------------------------------------------------------
# 2. One-Sided Upper Bound Range Tests (< 200)
# ------------------------------------------------------------------------------

def test_one_sided_upper_bound(flagger):
    # Total Cholesterol < 200 (crit_high = 200 * 2.0 = 400)
    t_norm = TestResult(test_name="Cholesterol", value=160.0, raw_value="160.0", ref_low=None, ref_high=200.0)
    assert flagger.determine_flag(t_norm) == FlagStatus.NORMAL

    t_boundary = TestResult(test_name="Cholesterol", value=200.0, raw_value="200.0", ref_low=None, ref_high=200.0)
    assert flagger.determine_flag(t_boundary) == FlagStatus.NORMAL

    t_high = TestResult(test_name="Cholesterol", value=248.0, raw_value="248.0", ref_low=None, ref_high=200.0)
    assert flagger.determine_flag(t_high) == FlagStatus.HIGH

    t_crit = TestResult(test_name="Cholesterol", value=420.0, raw_value="420.0", ref_low=None, ref_high=200.0)
    assert flagger.determine_flag(t_crit) == FlagStatus.CRITICAL_HIGH


# ------------------------------------------------------------------------------
# 3. One-Sided Lower Bound Range Tests (> 60)
# ------------------------------------------------------------------------------

def test_one_sided_lower_bound(flagger):
    # eGFR > 60 (crit_low = 60 / 2.0 = 30)
    t_norm = TestResult(test_name="eGFR", value=95.0, raw_value="95.0", ref_low=60.0, ref_high=None)
    assert flagger.determine_flag(t_norm) == FlagStatus.NORMAL

    t_boundary = TestResult(test_name="eGFR", value=60.0, raw_value="60.0", ref_low=60.0, ref_high=None)
    assert flagger.determine_flag(t_boundary) == FlagStatus.NORMAL

    t_low = TestResult(test_name="eGFR", value=45.0, raw_value="45.0", ref_low=60.0, ref_high=None)
    assert flagger.determine_flag(t_low) == FlagStatus.LOW

    t_crit = TestResult(test_name="eGFR", value=22.0, raw_value="22.0", ref_low=60.0, ref_high=None)
    assert flagger.determine_flag(t_crit) == FlagStatus.CRITICAL_LOW


# ------------------------------------------------------------------------------
# 4. Missing Range & Edge Case Tests
# ------------------------------------------------------------------------------

def test_missing_reference_range(flagger):
    t_no_range = TestResult(test_name="Experimental Analyte", value=42.0, raw_value="42.0", ref_low=None, ref_high=None)
    assert flagger.determine_flag(t_no_range) == FlagStatus.UNKNOWN


def test_zero_and_negative_values(flagger):
    # Zero value inside range
    t_zero_normal = TestResult(test_name="Bilirubin Direct", value=0.0, raw_value="0.0", ref_low=0.0, ref_high=0.3)
    assert flagger.determine_flag(t_zero_normal) == FlagStatus.NORMAL

    # Zero value below range
    t_zero_low = TestResult(test_name="Serum Potassium", value=0.0, raw_value="0.0", ref_low=3.5, ref_high=5.0)
    assert flagger.determine_flag(t_zero_low) == FlagStatus.CRITICAL_LOW

    # Negative value within range
    t_neg_normal = TestResult(test_name="Base Excess", value=-1.0, raw_value="-1.0", ref_low=-2.0, ref_high=2.0)
    assert flagger.determine_flag(t_neg_normal) == FlagStatus.NORMAL


# ------------------------------------------------------------------------------
# 5. Non-Numeric Qualitative Results
# ------------------------------------------------------------------------------

def test_non_numeric_abnormal(flagger):
    t_pos = TestResult(test_name="HBsAg", value=None, raw_value="Positive", ref_raw="Negative")
    assert flagger.determine_flag(t_pos) == FlagStatus.ABNORMAL

    t_react = TestResult(test_name="HIV Screen", value=None, raw_value="Reactive", ref_raw="Non-Reactive")
    assert flagger.determine_flag(t_react) == FlagStatus.ABNORMAL

    t_detect = TestResult(test_name="COVID PCR", value=None, raw_value="Detected", ref_raw="Not Detected")
    assert flagger.determine_flag(t_detect) == FlagStatus.ABNORMAL


def test_non_numeric_normal(flagger):
    t_neg = TestResult(test_name="Urine Ketones", value=None, raw_value="Negative", ref_raw="Negative")
    assert flagger.determine_flag(t_neg) == FlagStatus.NORMAL

    t_non_react = TestResult(test_name="VDRL", value=None, raw_value="Non-Reactive", ref_raw="Non-Reactive")
    assert flagger.determine_flag(t_non_react) == FlagStatus.NORMAL

    t_not_detect = TestResult(test_name="Malaria Antigen", value=None, raw_value="Not Detected", ref_raw="Not Detected")
    assert flagger.determine_flag(t_not_detect) == FlagStatus.NORMAL


def test_non_numeric_matching_ref(flagger):
    # Unmapped qualitative value matching reference string exactly
    t_trace = TestResult(test_name="Urine Protein", value=None, raw_value="Trace", ref_raw="Trace")
    assert flagger.determine_flag(t_trace) == FlagStatus.NORMAL

    # Unmapped qualitative value with no matching reference
    t_unrec = TestResult(test_name="Color", value=None, raw_value="Straw", ref_raw="")
    assert flagger.determine_flag(t_unrec) == FlagStatus.UNKNOWN


# ------------------------------------------------------------------------------
# 6. Full LabReport Batch Flagging
# ------------------------------------------------------------------------------

def test_flag_report_batch(flagger):
    tests = [
        TestResult(test_name="Hb", value=14.0, raw_value="14.0", ref_low=13.0, ref_high=17.0),
        TestResult(test_name="WBC", value=16000.0, raw_value="16,000", ref_low=4000.0, ref_high=11000.0),
        TestResult(test_name="HIV", value=None, raw_value="Non-Reactive", ref_raw="Non-Reactive"),
    ]
    report = LabReport(report_type="blood_test", tests=tests, extraction_method="pdfplumber")
    flagged_report = flagger.flag_report(report)

    assert flagged_report.tests[0].flag == FlagStatus.NORMAL
    assert flagged_report.tests[1].flag == FlagStatus.HIGH
    assert flagged_report.tests[2].flag == FlagStatus.NORMAL
