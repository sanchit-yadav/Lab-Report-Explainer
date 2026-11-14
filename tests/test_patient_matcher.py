"""Unit tests for the Patient Identity Matching and Cross-Contamination Isolation Engine."""

from src.extraction.patient_matcher import (
    are_reports_same_patient,
    group_reports_by_patient,
    normalize_patient_name,
)
from src.extraction.schema import LabReport


def test_normalize_patient_name():
    assert normalize_patient_name("Mr. Ramesh Kumar") == "ramesh kumar"
    assert normalize_patient_name("Dr. Priya Sharma") == "priya sharma"
    assert normalize_patient_name("Mrs Smt. Anjali Devi") == "anjali devi"
    assert normalize_patient_name("Master Aarav Gupta") == "aarav gupta"
    assert normalize_patient_name("Shri Rajesh V.") == "rajesh v"


def test_are_reports_same_patient_matching_titles():
    r1 = LabReport(patient_name="Mr. Ramesh Kumar", patient_gender="Male", patient_age="52 Y")
    r2 = LabReport(patient_name="Ramesh Kumar", patient_gender="Male", patient_age="52 Years")
    is_same, reason = are_reports_same_patient(r1, r2)
    assert is_same is True
    assert reason is None


def test_are_reports_same_patient_different_names():
    r1 = LabReport(patient_name="Ramesh Kumar", patient_gender="Male", patient_age="52 Y")
    r2 = LabReport(patient_name="Priya Sharma", patient_gender="Female", patient_age="31 Y")
    is_same, reason = are_reports_same_patient(r1, r2)
    assert is_same is False
    assert "Different patient names" in reason


def test_are_reports_same_patient_gender_mismatch():
    r1 = LabReport(patient_name="Kiran Patel", patient_gender="Male", patient_age="40")
    r2 = LabReport(patient_name="Kiran Patel", patient_gender="Female", patient_age="40")
    is_same, reason = are_reports_same_patient(r1, r2)
    assert is_same is False
    assert "Gender mismatch" in reason


def test_are_reports_same_patient_age_divergence():
    r1 = LabReport(patient_name="Aarav Sharma", patient_age="8 Y")
    r2 = LabReport(patient_name="Aarav Sharma", patient_age="45 Y")
    is_same, reason = are_reports_same_patient(r1, r2)
    assert is_same is False
    assert "age difference" in reason.lower()


def test_group_reports_by_patient_multi_cohort():
    r1 = LabReport(patient_name="Mr. Ramesh Kumar", patient_gender="Male", patient_age="52 Y", report_date="10-Jan-2026")
    r2 = LabReport(patient_name="Priya Sharma", patient_gender="Female", patient_age="31 Y", report_date="15-Jan-2026")
    r3 = LabReport(patient_name="Ramesh Kumar", patient_gender="Male", patient_age="52 Y", report_date="20-Feb-2026")

    match_res = group_reports_by_patient([r1, r2, r3])
    assert match_res.is_single_patient is False
    assert len(match_res.patient_groups) == 2
    assert "Cross-contamination" in match_res.warning_message_en or "Patient Mismatch Detected" in match_res.warning_message_en
    assert match_res.warning_message_hi is not None
