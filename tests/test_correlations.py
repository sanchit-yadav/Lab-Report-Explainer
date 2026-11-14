"""Unit tests for the deterministic Cross-Analyte Correlation Engine."""

from src.extraction.schema import FlagStatus, TestResult
from src.flagging.correlations import CorrelationEngine, CorrelationSeverity


def test_lipid_cardiovascular_ratios():
    engine = CorrelationEngine()
    tests = [
        TestResult(test_name="Total Cholesterol", value=240.0, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="HDL Cholesterol", value=40.0, unit="mg/dL", flag=FlagStatus.LOW),
        TestResult(test_name="Triglycerides", value=220.0, unit="mg/dL", flag=FlagStatus.HIGH),
    ]
    correlations = engine.evaluate(tests)
    assert len(correlations) == 2

    # TC / HDL = 240 / 40 = 6.0 (Elevated > 5.0)
    tc_hdl = next(c for c in correlations if "Total Cholesterol / HDL" in c.title)
    assert tc_hdl.value == 6.0
    assert tc_hdl.severity == CorrelationSeverity.ELEVATED
    assert len(tc_hdl.doctor_questions) >= 2

    # TG / HDL = 220 / 40 = 5.5 (Elevated > 3.8)
    tg_hdl = next(c for c in correlations if "Triglyceride / HDL" in c.title)
    assert tg_hdl.value == 5.5
    assert tg_hdl.severity == CorrelationSeverity.ELEVATED


def test_liver_de_ritis_ratio():
    engine = CorrelationEngine()

    # Scenario A: Alcoholic / toxic pattern (AST/ALT > 2.0 with elevated enzymes)
    tests_a = [
        TestResult(test_name="SGOT (AST)", value=120.0, unit="U/L", flag=FlagStatus.HIGH),
        TestResult(test_name="SGPT (ALT)", value=50.0, unit="U/L", flag=FlagStatus.HIGH),
    ]
    corrs_a = engine.evaluate(tests_a)
    de_ritis_a = next(c for c in corrs_a if "De Ritis" in c.title)
    assert de_ritis_a.value == 2.4
    assert de_ritis_a.severity == CorrelationSeverity.HIGH

    # Scenario B: NAFLD / Fatty liver pattern (AST/ALT < 1.0 with elevated enzymes)
    tests_b = [
        TestResult(test_name="AST", value=45.0, unit="U/L", flag=FlagStatus.HIGH),
        TestResult(test_name="ALT", value=90.0, unit="U/L", flag=FlagStatus.HIGH),
    ]
    corrs_b = engine.evaluate(tests_b)
    de_ritis_b = next(c for c in corrs_b if "De Ritis" in c.title)
    assert de_ritis_b.value == 0.5
    assert de_ritis_b.severity == CorrelationSeverity.BORDERLINE


def test_renal_bun_creatinine_ratio_with_urea_conversion():
    engine = CorrelationEngine()

    # Serum Urea = 64.2 mg/dL -> BUN ≈ 64.2 / 2.14 = 30.0 mg/dL
    # Creatinine = 1.0 mg/dL -> Ratio = 30:1 (Dehydration / Prerenal > 20:1)
    tests = [
        TestResult(test_name="Blood Urea", value=64.2, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="Serum Creatinine", value=1.0, unit="mg/dL", flag=FlagStatus.NORMAL),
    ]
    correlations = engine.evaluate(tests)
    bun_cr = next(c for c in correlations if "BUN / Serum Creatinine" in c.title)
    assert bun_cr.value == 30.0
    assert bun_cr.severity == CorrelationSeverity.ELEVATED


def test_anemia_microcytic_phenotype():
    engine = CorrelationEngine()
    tests = [
        TestResult(test_name="Hemoglobin", value=9.5, unit="g/dL", flag=FlagStatus.LOW),
        TestResult(test_name="MCV", value=68.0, unit="fL", flag=FlagStatus.LOW),
    ]
    correlations = engine.evaluate(tests)
    anemia = next(c for c in correlations if "Anemia" in c.title)
    assert anemia.severity == CorrelationSeverity.HIGH
    assert "Microcytic" in anemia.finding_en
    assert "माइक्रोसिटिक" in anemia.finding_hi


def test_glycemic_discordance():
    engine = CorrelationEngine()
    # High Fasting Glucose + Normal HbA1c
    tests = [
        TestResult(test_name="Fasting Blood Sugar", value=138.0, unit="mg/dL", flag=FlagStatus.HIGH),
        TestResult(test_name="HbA1c", value=5.4, unit="%", flag=FlagStatus.NORMAL),
    ]
    correlations = engine.evaluate(tests)
    glycemic = next(c for c in correlations if "Glycemic Concordance" in c.title)
    assert glycemic.severity == CorrelationSeverity.BORDERLINE
    assert "acute discrepancy" in glycemic.finding_en.lower()
