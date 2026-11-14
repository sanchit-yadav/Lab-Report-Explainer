"""Unit tests for the Medication & Supplement Interference Checker."""

from src.extraction.schema import FlagStatus, TestResult
from src.flagging.interferences import DrugInterferenceEngine


def test_drug_interference_detects_biotin_thyroid():
    engine = DrugInterferenceEngine()
    tests = [
        TestResult(test_name="TSH - Thyroid Stimulating Hormone", value=0.05, unit="uIU/mL", flag=FlagStatus.LOW),
        TestResult(test_name="Free T4", value=3.2, unit="ng/dL", flag=FlagStatus.HIGH),
    ]
    interferences = engine.evaluate(tests)
    assert len(interferences) >= 1
    subs = [i.substance_name for i in interferences]
    assert any("Biotin" in s for s in subs)
    biotin_item = next(i for i in interferences if "Biotin" in i.substance_name)
    assert "streptavidin" in biotin_item.clinical_mechanism_en.lower()
    assert "48 to 72 hours" in biotin_item.guidance_en.lower()


def test_drug_interference_detects_statin_transaminases():
    engine = DrugInterferenceEngine()
    tests = [
        TestResult(test_name="SGPT (ALT)", value=68.0, unit="U/L", flag=FlagStatus.HIGH),
        TestResult(test_name="SGOT (AST)", value=55.0, unit="U/L", flag=FlagStatus.HIGH),
    ]
    interferences = engine.evaluate(tests)
    assert any("Statin" in i.substance_name for i in interferences)


def test_drug_interference_creatine_and_ace_inhibitors():
    engine = DrugInterferenceEngine()
    tests = [
        TestResult(test_name="Serum Creatinine", value=1.6, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="Potassium", value=5.5, unit="mEq/L", flag=FlagStatus.HIGH),
    ]
    interferences = engine.evaluate(tests)
    subs = [i.substance_name for i in interferences]
    assert any("Creatine" in s for s in subs)
    assert any("ACE Inhibitors" in s for s in subs)
