"""Unit tests for longitudinal history tracking and trend analysis."""

from pathlib import Path
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.history.tracker import HistoryTracker, TrendDirection


def test_history_tracker_delta_and_improving_trajectory(tmp_path):
    tracker = HistoryTracker(storage_dir=tmp_path)

    # Report 1 (3 months ago): Elevated Cholesterol 250 mg/dL
    rep1 = LabReport(
        patient_name="Ramesh Kumar",
        report_date="15-Jan-2026",
        tests=[
            TestResult(test_name="Total Cholesterol", value=250.0, unit="mg/dL", flag=FlagStatus.HIGH),
            TestResult(test_name="Hemoglobin", value=13.5, unit="g/dL", flag=FlagStatus.NORMAL),
        ],
    )

    # Report 2 (Today): Improved Cholesterol 210 mg/dL
    rep2 = LabReport(
        patient_name="Ramesh Kumar",
        report_date="15-Apr-2026",
        tests=[
            TestResult(test_name="Total Cholesterol", value=210.0, unit="mg/dL", flag=FlagStatus.HIGH),
            TestResult(test_name="Hemoglobin", value=13.6, unit="g/dL", flag=FlagStatus.NORMAL),
        ],
    )

    tracker.add_reports([rep1, rep2])
    trends = tracker.get_analyte_trends()

    assert "Total Cholesterol" in trends
    chol_trend = trends["Total Cholesterol"]
    assert len(chol_trend.data_points) == 2
    assert chol_trend.delta_absolute == -40.0
    assert chol_trend.delta_percent == -16.0
    assert chol_trend.direction == TrendDirection.IMPROVING
    assert "positive clinical improvement" in chol_trend.narrative_en

    # Hemoglobin remained stable
    hb_trend = trends["Hemoglobin"]
    assert hb_trend.direction == TrendDirection.STABLE

    # Verify JSON persistence
    persisted = tmp_path / "patient_history.json"
    assert persisted.exists()

    # Verify reload from disk
    new_tracker = HistoryTracker(storage_dir=tmp_path)
    new_tracker.load_from_disk()
    assert len(new_tracker.reports) == 2


def test_history_tracker_worsening_trajectory():
    tracker = HistoryTracker()

    rep1 = LabReport(
        patient_name="Sunita Sharma",
        report_date="10/01/2026",
        tests=[
            TestResult(test_name="HbA1c", value=6.2, unit="%", flag=FlagStatus.HIGH),
        ],
    )
    rep2 = LabReport(
        patient_name="Sunita Sharma",
        report_date="10/04/2026",
        tests=[
            TestResult(test_name="HbA1c", value=7.4, unit="%", flag=FlagStatus.HIGH),
        ],
    )
    tracker.add_reports([rep1, rep2])
    trends = tracker.get_analyte_trends()

    hba1c_trend = trends["HbA1c"]
    assert hba1c_trend.delta_absolute == 1.2
    assert hba1c_trend.direction == TrendDirection.WORSENING
    assert "प्रतिकूल" in hba1c_trend.narrative_hi
