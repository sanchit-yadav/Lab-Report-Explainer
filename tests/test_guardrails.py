"""Unit tests for Layer 1 Input Guard and Layer 3 Output Guard."""

import pytest
from src.explainer.schema import TestExplanation
from src.extraction.schema import FlagStatus
from src.guardrails.input_guard import InputGuard
from src.guardrails.output_guard import OutputGuard


@pytest.fixture
def input_guard():
    return InputGuard()


@pytest.fixture
def output_guard():
    return OutputGuard()


# ------------------------------------------------------------------------------
# 1. Layer 1 Input Guard Tests
# ------------------------------------------------------------------------------

def test_input_guard_blocks_diagnosis_requests(input_guard):
    res1 = input_guard.check("Based on my report, do I have diabetes?")
    assert res1.blocked is True
    assert "doctor" in res1.safe_response_en.lower()

    res2 = input_guard.check("Does this elevated WBC mean I have leukemia?")
    assert res2.blocked is True


def test_input_guard_blocks_medication_and_dosage(input_guard):
    res1 = input_guard.check("What medicine should I take for high cholesterol?")
    assert res1.blocked is True

    res2 = input_guard.check("How many mg of atorvastatin should I take daily?")
    assert res2.blocked is True


def test_input_guard_blocks_hindi_injections(input_guard):
    res1 = input_guard.check("मेरी रिपोर्ट देखकर बताओ कौन सी बीमारी है?")
    assert res1.blocked is True
    assert "डॉक्टर" in res1.safe_response_hi

    res2 = input_guard.check("कोलेस्ट्रॉल कम करने के लिए कौन सी दवाई लूं?")
    assert res2.blocked is True


def test_input_guard_allows_safe_educational_queries(input_guard):
    safe1 = input_guard.check("What does hemoglobin measure in a complete blood count?")
    assert safe1.blocked is False

    safe2 = input_guard.check("Why is my WBC count marked high?")
    assert safe2.blocked is False

    safe3 = input_guard.check("What questions should I ask my doctor about my cholesterol?")
    assert safe3.blocked is False


# ------------------------------------------------------------------------------
# 2. Layer 3 Output Guard Tests
# ------------------------------------------------------------------------------

def test_output_guard_redacts_drug_names(output_guard):
    unsafe_text = "You should start taking metformin 500mg and atorvastatin daily."
    sanitized, violations = output_guard.sanitize_text(unsafe_text, lang="en")
    assert violations >= 2
    assert "metformin" not in sanitized.lower()
    assert "atorvastatin" not in sanitized.lower()
    assert "[Medication - Consult Doctor]" in sanitized


def test_output_guard_redacts_diagnostic_phrases(output_guard):
    unsafe_text = "This result indicates that you have kidney disease."
    sanitized, violations = output_guard.sanitize_text(unsafe_text, lang="en")
    assert violations >= 1
    assert "you have kidney disease" not in sanitized.lower()


def test_output_guard_preserves_clean_explanation(output_guard):
    explanation = TestExplanation(
        test_name="Hemoglobin",
        flag=FlagStatus.HIGH,
        explanation_en="Hemoglobin carries oxygen in your red blood cells. Elevated levels can reflect dehydration.",
        explanation_hi="हीमोग्लोबिन लाल रक्त कोशिकाओं में ऑक्सीजन ले जाता है।",
        source_urls=["https://medlineplus.gov"],
        doctor_questions=["What is causing my elevated hemoglobin?"],
        disclaimer="",
    )
    cleaned = output_guard.check(explanation)
    assert "Hemoglobin carries oxygen" in cleaned.explanation_en
    assert cleaned.disclaimer != ""  # Auto-appended disclaimer
