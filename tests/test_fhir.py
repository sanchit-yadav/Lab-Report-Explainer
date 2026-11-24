"""Unit tests for HL7 FHIR Release 4 resource and Bundle generation."""

from __future__ import annotations

import base64

from src.explainer.schema import ReportExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.interop.fhir_export import FHIRExporter


def test_test_result_to_fhir_observation():
    """Individual analyte maps to a valid FHIR R4 Observation resource."""
    test = TestResult(
        test_name="Serum Potassium",
        value=6.2,
        unit="mEq/L",
        ref_low=3.5,
        ref_high=5.1,
        ref_raw="3.5 - 5.1",
        flag=FlagStatus.CRITICAL_HIGH,
    )

    obs = FHIRExporter.test_result_to_observation(
        test=test,
        patient_id="patient-123",
        patient_name="Sameer Verma",
        effective_time="2026-11-15T10:00:00Z",
    )

    assert obs["resourceType"] == "Observation"
    assert obs["status"] == "final"
    assert obs["code"]["coding"][0]["system"] == "http://loinc.org"
    assert obs["code"]["coding"][0]["code"] == "2823-3"  # Potassium
    assert obs["valueQuantity"]["value"] == 6.2
    assert obs["valueQuantity"]["unit"] == "mEq/L"
    assert obs["interpretation"][0]["coding"][0]["code"] == "HH"  # Critical high
    assert obs["referenceRange"][0]["low"]["value"] == 3.5
    assert obs["referenceRange"][0]["high"]["value"] == 5.1


def test_create_fhir_diagnostic_report_and_bundle():
    """Complete report exports as a valid FHIR R4 Collection Bundle."""
    report = LabReport(
        patient_name="Ananya Sen",
        patient_age="34 Y",
        patient_gender="F",
        report_date="2026-11-15",
        lab_name="SRL Diagnostics",
        tests=[
            TestResult(
                test_name="Total Cholesterol",
                value=245.0,
                unit="mg/dL",
                ref_low=100.0,
                ref_high=200.0,
                flag=FlagStatus.HIGH,
            ),
            TestResult(
                test_name="Fasting Blood Glucose",
                value=92.0,
                unit="mg/dL",
                ref_low=70.0,
                ref_high=99.0,
                flag=FlagStatus.NORMAL,
            ),
        ],
    )

    explanation = ReportExplanation(
        patient_name="Ananya Sen",
        report_summary_en="Patient presents with elevated total cholesterol.",
        report_summary_hi="मरीज में कोलेस्ट्रॉल का स्तर बढ़ा हुआ है।",
        total_tests=2,
        flagged_count=1,
    )

    dummy_pdf = b"%PDF-1.4 Mock Brief Data"
    bundle = FHIRExporter.create_diagnostic_report(report, explanation, dummy_pdf)

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["total"] == 3  # 1 DiagnosticReport + 2 Observations

    # 1st entry is DiagnosticReport
    diag_res = bundle["entry"][0]["resource"]
    assert diag_res["resourceType"] == "DiagnosticReport"
    assert diag_res["subject"]["display"] == "Ananya Sen"
    assert "elevated total cholesterol" in diag_res["conclusion"]
    assert len(diag_res["result"]) == 2
    assert diag_res["presentedForm"][0]["contentType"] == "application/pdf"
    assert base64.b64decode(diag_res["presentedForm"][0]["data"]) == dummy_pdf

    # 2nd entry is Total Cholesterol Observation
    obs_chol = bundle["entry"][1]["resource"]
    assert obs_chol["code"]["coding"][0]["code"] == "2093-3"
    assert obs_chol["interpretation"][0]["coding"][0]["code"] == "H"
