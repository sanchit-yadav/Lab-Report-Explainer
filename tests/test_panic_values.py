"""Unit tests for the Critical Panic Value Emergency Protocol."""

from src.extraction.schema import FlagStatus, TestResult
from src.flagging.panic_values import PanicSeverity, PanicValueEngine


def test_panic_value_engine_detects_severe_hyperkalemia():
    engine = PanicValueEngine()
    tests = [
        TestResult(test_name="Serum Potassium", value=6.5, unit="mEq/L", flag=FlagStatus.CRITICAL_HIGH),
        TestResult(test_name="Serum Sodium", value=138.0, unit="mEq/L", flag=FlagStatus.NORMAL),
    ]
    alerts = engine.evaluate(tests)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.test_name == "Serum Potassium"
    assert alert.observed_value == 6.5
    assert alert.severity == PanicSeverity.IMMEDIATE_EMERGENCY
    assert "hyperkalemia" in alert.clinical_risk_en.lower()
    assert "emergency" in alert.action_protocol_en.lower()
    assert len(alert.doctor_questions) >= 1


def test_panic_value_engine_detects_critical_hypoglycemia_and_anemia():
    engine = PanicValueEngine()
    tests = [
        TestResult(test_name="Fasting Blood Sugar", value=42.0, unit="mg/dL", flag=FlagStatus.CRITICAL_LOW),
        TestResult(test_name="Hemoglobin", value=6.2, unit="g/dL", flag=FlagStatus.CRITICAL_LOW),
    ]
    alerts = engine.evaluate(tests)
    assert len(alerts) == 2
    names = [a.test_name for a in alerts]
    assert "Fasting Blood Sugar" in names
    assert "Hemoglobin" in names


def test_panic_value_engine_ignores_normal_and_mildly_elevated_values():
    engine = PanicValueEngine()
    tests = [
        TestResult(test_name="Potassium", value=5.3, unit="mEq/L", flag=FlagStatus.HIGH),  # High, but not panic (>6.2)
        TestResult(test_name="Hemoglobin", value=10.4, unit="g/dL", flag=FlagStatus.LOW),  # Low, but not panic (<7.0)
        TestResult(test_name="Platelet Count", value=150000, unit="/cumm", flag=FlagStatus.NORMAL),
    ]
    alerts = engine.evaluate(tests)
    assert len(alerts) == 0
