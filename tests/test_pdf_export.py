"""Unit tests for the Doctor Discussion Brief PDF export module."""

from src.explainer.pdf_export import generate_doctor_brief_pdf
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult


def test_generate_doctor_brief_pdf_valid_bytes():
    """Verify that a valid PDF byte string is generated with header and table."""
    raw_report = LabReport(
        patient_name="Priya Sharma",
        report_date="2026-10-15",
        lab_name="Metropolis Healthcare",
        tests=[
            TestResult(
                test_name="Hemoglobin",
                value=11.2,
                raw_value="11.2",
                unit="g/dL",
                ref_low=12.0,
                ref_high=15.0,
                ref_raw="12.0 - 15.0",
                flag=FlagStatus.LOW,
            ),
            TestResult(
                test_name="Platelet Count",
                value=210000.0,
                raw_value="210,000",
                unit="cells/cumm",
                ref_low=150000.0,
                ref_high=450000.0,
                ref_raw="150,000 - 450,000",
                flag=FlagStatus.NORMAL,
            ),
        ],
    )

    explanation = ReportExplanation(
        patient_name="Priya Sharma",
        report_date="2026-10-15",
        report_summary_en="Patient has a slightly low hemoglobin count requiring clinical attention.",
        report_summary_hi="मरीज का हीमोग्लोबिन स्तर थोड़ा कम है।",
        test_explanations=[
            TestExplanation(
                test_name="Hemoglobin",
                flag=FlagStatus.LOW,
                explanation_en="Hemoglobin is the iron-rich protein in red blood cells that carries oxygen.",
                explanation_hi="हीमोग्लोबिन लाल रक्त कोशिकाओं में पाया जाने वाला प्रोटीन है।",
                source_urls=["https://medlineplus.gov/lab-tests/hemoglobin/"],
                doctor_questions=["Should I be evaluated for iron deficiency or dietary anemia?"],
            )
        ],
        flagged_count=1,
        total_tests=2,
        raw_report=raw_report,
    )

    pdf_bytes = generate_doctor_brief_pdf(explanation, lang="en")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")  # Valid PDF header


def test_generate_doctor_brief_pdf_with_correlations():
    """Verify that Doctor Brief PDF embeds clinical correlation tables and findings."""
    from src.flagging.correlations import ClinicalCorrelation, CorrelationSeverity

    corr = ClinicalCorrelation(
        panel_name="Lipid Profile",
        title="Total Cholesterol / HDL Ratio",
        value=5.4,
        unit="ratio",
        optimal_range="< 3.5",
        severity=CorrelationSeverity.ELEVATED,
        finding_en="Total cholesterol to HDL ratio is elevated at 5.4.",
        finding_hi="कुल कोलेस्ट्रॉल / एचडीएल अनुपात 5.4 पर बढ़ा हुआ है।",
        doctor_questions=["How does this ratio impact my cardiovascular risk?"],
    )

    explanation = ReportExplanation(
        patient_name="Anil Verma",
        report_date="2026-10-18",
        report_summary_en="Lipid evaluation shows elevated cardiovascular ratio.",
        report_summary_hi="लिपिड जांच में बढ़ा हुआ हृदय जोखिम अनुपात देखा गया।",
        test_explanations=[],
        correlations=[corr],
        flagged_count=1,
        total_tests=2,
    )

    pdf_bytes = generate_doctor_brief_pdf(explanation, lang="en")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")

