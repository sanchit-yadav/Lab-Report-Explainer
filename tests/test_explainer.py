"""Unit tests for explanation generator and prompt construction."""

import pytest
from src.explainer.generator import ExplanationGenerator
from src.explainer.prompts import build_explanation_prompt, get_system_prompt
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult


@pytest.fixture
def generator():
    return ExplanationGenerator()


def test_system_prompt_contains_safety_rules():
    sys_prompt = get_system_prompt()
    assert "NEVER diagnose" in sys_prompt
    assert "NEVER prescribe" in sys_prompt
    assert "doctor" in sys_prompt.lower()


def test_build_explanation_prompt():
    test = TestResult(
        test_name="Total Cholesterol",
        value=248.0,
        raw_value="248.0",
        unit="mg/dL",
        ref_raw="< 200",
        flag=FlagStatus.HIGH,
    )
    prompt = build_explanation_prompt(
        test=test,
        context_chunks=["Cholesterol is a fat-like substance."],
        source_urls=["https://medlineplus.gov"],
    )
    assert "Total Cholesterol" in prompt
    assert "248.0 mg/dL" in prompt
    assert "HIGH" in prompt
    assert "https://medlineplus.gov" in prompt


def test_explain_test_returns_valid_schema(generator):
    test = TestResult(
        test_name="Serum Creatinine",
        value=1.80,
        raw_value="1.80",
        unit="mg/dL",
        ref_low=0.60,
        ref_high=1.20,
        ref_raw="0.60 - 1.20",
        flag=FlagStatus.HIGH,
    )
    candidates = [
        {
            "id": "serum_creatinine",
            "text": "Creatinine is a waste product filtered by the kidneys.",
            "metadata": {"source_url": "https://medlineplus.gov/lab-tests/creatinine-test/"},
        }
    ]
    explanation = generator.explain_test(test, candidates)
    assert isinstance(explanation, TestExplanation)
    assert explanation.test_name == "Serum Creatinine"
    assert len(explanation.explanation_en) > 20
    assert len(explanation.explanation_hi) > 20
    assert len(explanation.doctor_questions) >= 2
    assert "https://medlineplus.gov/lab-tests/creatinine-test/" in explanation.source_urls


def test_explain_report_assembles_summary(generator):
    tests = [
        TestResult(test_name="Hb", value=14.0, raw_value="14.0", flag=FlagStatus.NORMAL),
        TestResult(test_name="Cholesterol", value=250.0, raw_value="250.0", flag=FlagStatus.HIGH),
    ]
    report = LabReport(
        patient_name="Rahul Sharma",
        report_date="2026-10-15",
        tests=tests,
        extraction_method="pdfplumber",
    )
    test_exps = [
        TestExplanation(
            test_name="Cholesterol",
            flag=FlagStatus.HIGH,
            explanation_en="High cholesterol explanation",
            explanation_hi="उच्च कोलेस्ट्रॉल विवरण",
        )
    ]
    report_exp = generator.explain_report(report, test_exps)
    assert isinstance(report_exp, ReportExplanation)
    assert report_exp.patient_name == "Rahul Sharma"
    assert report_exp.total_tests == 2
    assert report_exp.flagged_count == 1
    assert len(report_exp.test_explanations) == 1
