"""Unit tests for the Evidence-Based Lifestyle & Nutrition Guidance Engine."""

from src.extraction.schema import FlagStatus, TestResult
from src.flagging.lifestyle import LifestyleEngine


def test_lifestyle_engine_detects_dyslipidemia():
    engine = LifestyleEngine()
    tests = [
        TestResult(test_name="Total Cholesterol", value=245.0, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="Triglycerides", value=220.0, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="HDL Cholesterol", value=35.0, unit="mg/dL", flag=FlagStatus.LOW),
    ]
    guidance = engine.evaluate(tests)
    assert len(guidance) >= 1
    lipid_g = next(g for g in guidance if "Cardiovascular" in g.panel_name)
    assert "Mediterranean" in lipid_g.nutrition_title_en
    assert any("soluble" in r.lower() for r in lipid_g.key_recommendations_en)
    assert "Oats & Barley" in lipid_g.foods_to_favor_en


def test_lifestyle_engine_detects_glycemic_and_liver():
    engine = LifestyleEngine()
    tests = [
        TestResult(test_name="Fasting Blood Sugar", value=140.0, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="HbA1c", value=7.2, unit="%", flag=FlagStatus.HIGH),
        TestResult(test_name="SGPT (ALT)", value=75.0, unit="U/L", flag=FlagStatus.HIGH),
    ]
    guidance = engine.evaluate(tests)
    panels = [g.panel_name for g in guidance]
    assert any("Glycemic" in p for p in panels)
    assert any("Hepatic" in p for p in panels)


def test_lifestyle_engine_ignores_all_normal_tests():
    engine = LifestyleEngine()
    tests = [
        TestResult(test_name="Total Cholesterol", value=170.0, unit="mg/dL", flag=FlagStatus.NORMAL),
        TestResult(test_name="Fasting Blood Sugar", value=85.0, unit="mg/dL", flag=FlagStatus.NORMAL),
    ]
    guidance = engine.evaluate(tests)
    assert len(guidance) == 0
