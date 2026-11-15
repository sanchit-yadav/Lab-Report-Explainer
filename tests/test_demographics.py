"""Unit tests for demographic reference interval stratification matrix."""

from __future__ import annotations

import pytest

from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.flagging.demographics import DemographicContext, DemographicIntervalEngine


def test_parse_demographics_age_and_gender():
    """Various real-world patient age and gender strings are parsed into clean metadata."""
    d1 = DemographicIntervalEngine.parse_demographics("45 Y", "Male")
    assert d1.age_years == 45.0
    assert d1.sex == "M"
    assert d1.is_pediatric is False
    assert d1.is_geriatric is False

    d2 = DemographicIntervalEngine.parse_demographics("6 Months", "Female")
    assert d2.age_years == 0.5
    assert d2.sex == "F"
    assert d2.is_pediatric is True

    d3 = DemographicIntervalEngine.parse_demographics("78", "F")
    assert d3.age_years == 78.0
    assert d3.sex == "F"
    assert d3.is_geriatric is True


def test_demographic_stratification_hemoglobin_sex_differences():
    """Adult Male and Female Hemoglobin brackets apply sex-specific reference limits."""
    test_male = TestResult(test_name="Hemoglobin", value=13.0, unit="g/dL")
    demo_male = DemographicContext(age_years=35.0, sex="M")
    low_m, high_m, note_m = DemographicIntervalEngine.refine_analyte_range(test_male, demo_male)
    assert low_m == 13.5
    assert high_m == 17.5

    test_female = TestResult(test_name="Hemoglobin", value=13.0, unit="g/dL")
    demo_female = DemographicContext(age_years=35.0, sex="F")
    low_f, high_f, note_f = DemographicIntervalEngine.refine_analyte_range(test_female, demo_female)
    assert low_f == 12.0
    assert high_f == 15.5


def test_demographic_stratification_pediatric_alp():
    """Child Alkaline Phosphatase adjusts for physiological bone growth elevation."""
    test_child_alp = TestResult(
        test_name="Alkaline Phosphatase",
        value=280.0,
        unit="U/L",
        ref_low=44.0,
        ref_high=147.0,  # Generic adult range printed on report
    )
    demo_child = DemographicContext(age_years=9.0, sex="M", is_pediatric=True)

    low_p, high_p, note_p = DemographicIntervalEngine.refine_analyte_range(test_child_alp, demo_child)
    assert high_p == 390.0  # Child upper limit is 390 U/L
    assert "bone-growth" in note_p.lower()


def test_apply_demographic_stratification_to_report():
    """Applying engine to a complete report refines all matching tests."""
    report = LabReport(
        patient_name="Baby Aarav",
        patient_age="8 Months",
        patient_gender="Male",
        tests=[
            TestResult(test_name="Hemoglobin", value=11.0, unit="g/dL"),  # Normal for infant (10.0-14.0)
            TestResult(test_name="Serum Creatinine", value=0.4, unit="mg/dL"),  # Normal for child (0.3-0.7)
        ],
    )

    refined = DemographicIntervalEngine.apply_demographic_stratification(report)

    assert refined.tests[0].ref_low == 10.0
    assert refined.tests[0].ref_high == 14.0
    assert refined.tests[1].ref_low == 0.3
    assert refined.tests[1].ref_high == 0.7
