"""Unit tests for HIPAA/GDPR PHI De-identification and surrogate tokenization."""

from __future__ import annotations

import pytest

from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.privacy.deidentifier import PHIDeidentifier


@pytest.fixture
def deidentifier():
    return PHIDeidentifier()


def test_deidentify_patient_names_and_prefixes(deidentifier):
    """Patient names following headers or honorifics are de-identified."""
    text = (
        "Patient Name: Rajesh Sharma\n"
        "Consultant: Dr. A. K. Gupta\n"
        "Attendant: Mr. Amit Verma\n"
        "Serum Cholesterol: 240 mg/dL"
    )
    res = deidentifier.anonymize_text(text)

    assert res.has_phi is True
    assert "Rajesh Sharma" not in res.sanitized_text
    assert "A. K. Gupta" not in res.sanitized_text
    assert "[PATIENT_NAME_1]" in res.sanitized_text or "[DOCTOR_1]" in res.sanitized_text
    assert "240 mg/dL" in res.sanitized_text  # Clinical biomarker values are strictly preserved!


def test_deidentify_emails_and_phones(deidentifier):
    """Direct contact identifiers (email, telephone) are replaced with surrogate tokens."""
    text = (
        "Report for patient contacting at rahul.sharma@example.com or +91 9876543210. "
        "Emergency phone: (555) 234-5678."
    )
    res = deidentifier.anonymize_text(text)

    assert "rahul.sharma@example.com" not in res.sanitized_text
    assert "+91 9876543210" not in res.sanitized_text
    assert "(555) 234-5678" not in res.sanitized_text
    assert "[EMAIL_1]" in res.sanitized_text
    assert "[PHONE_1]" in res.sanitized_text


def test_deidentify_mrn_and_identifiers(deidentifier):
    """Hospital accession numbers, MRNs, and sample IDs are redacted."""
    text = (
        "Hospital ID: MRN-98241A, UHID: 1004829, Sample ID: SMP-84920. "
        "Glucose Fasting: 110 mg/dL."
    )
    res = deidentifier.anonymize_text(text)

    assert "98241A" not in res.sanitized_text
    assert "1004829" not in res.sanitized_text
    assert "SMP-84920" not in res.sanitized_text
    assert "110 mg/dL" in res.sanitized_text


def test_deidentify_dates_of_birth(deidentifier):
    """Dates of birth are masked according to HIPAA Safe Harbor."""
    text = "Patient DOB: 14/05/1988, Born: May 14, 1988. Hemoglobin: 13.5 g/dL."
    res = deidentifier.anonymize_text(text)

    assert "14/05/1988" not in res.sanitized_text
    assert "[DOB_" in res.sanitized_text
    assert "13.5 g/dL" in res.sanitized_text


def test_bidirectional_de_anonymization(deidentifier):
    """Surrogate tokens can be accurately restored locally with the entity mapping."""
    raw_text = "Patient Name: Sneha Patel, Phone: 9876543210"
    anon_res = deidentifier.anonymize_text(raw_text)

    assert "Sneha Patel" not in anon_res.sanitized_text

    restored = deidentifier.de_anonymize_text(anon_res.sanitized_text, anon_res.entity_mapping)
    assert restored == raw_text


def test_anonymize_lab_report_struct(deidentifier):
    """Structured LabReport objects have patient metadata safely masked."""
    report = LabReport(
        patient_name="Vikas Malhotra",
        patient_age="48 Y",
        patient_gender="M",
        lab_name="Metropolis Healthcare Ltd",
        tests=[
            TestResult(test_name="Triglycerides", value=185.0, unit="mg/dL", flag=FlagStatus.HIGH)
        ],
    )

    sanitized, mapping = deidentifier.anonymize_lab_report(report)

    assert sanitized.patient_name == "[PATIENT_NAME_1]"
    assert sanitized.lab_name == "[CLINICAL_LAB_1]"
    assert "[PATIENT_NAME_1]" in mapping
    assert mapping["[PATIENT_NAME_1]"] == "Vikas Malhotra"

    # Original report object remains untouched
    assert report.patient_name == "Vikas Malhotra"
    assert sanitized.tests[0].value == 185.0


def test_de_anonymize_bilingual_explanation(deidentifier):
    """Surrogate tokens are re-hydrated in both English and Hindi text."""
    exp_en = "This report for [PATIENT_NAME_1] indicates elevated cholesterol."
    exp_hi = "[PATIENT_NAME_1] की इस रिपोर्ट में कोलेस्ट्रॉल बढ़ा हुआ पाया गया है।"
    mapping = {"[PATIENT_NAME_1]": "Kavita Rao"}

    res_en, res_hi = deidentifier.de_anonymize_explanation(exp_en, exp_hi, mapping)

    assert "Kavita Rao" in res_en
    assert "Kavita Rao" in res_hi
    assert "[PATIENT_NAME_1]" not in res_en
    assert "[PATIENT_NAME_1]" not in res_hi
