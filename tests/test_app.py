"""Smoke tests for the Streamlit application configuration and constants."""

from pathlib import Path
from app import SAMPLE_OPTIONS, FLAG_BADGES, FLAG_COLORS
from src.extraction.schema import FlagStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_reports"


def test_sample_options_exist_on_disk():
    """Verify that every sample report referenced in app.py exists."""
    for label, filename in SAMPLE_OPTIONS.items():
        sample_path = SAMPLE_DIR / filename
        assert sample_path.exists(), f"Sample report file missing: {sample_path}"


def test_flag_mappings_complete():
    """Ensure all FlagStatus enum variants have corresponding badge/color entries."""
    for status in FlagStatus:
        assert status in FLAG_COLORS
        assert status in FLAG_BADGES


def test_render_range_gauge_html():
    """Verify that visual range gauges generate correct HTML components for numeric tests."""
    from app import render_range_gauge_html
    from src.extraction.schema import TestResult

    # Two-sided range (Hemoglobin)
    t_two_sided = TestResult(
        test_name="Hemoglobin",
        value=11.2,
        unit="g/dL",
        ref_low=12.0,
        ref_high=15.0,
        flag=FlagStatus.LOW,
    )
    html1 = render_range_gauge_html(t_two_sided)
    assert "Optimal Range: 12.0 - 15.0 g/dL" in html1
    assert "11.2" in html1
    assert "width:" in html1
    # Verify no line has leading whitespace that could trigger Markdown code blocks
    assert not any(line.startswith("    ") for line in html1.splitlines())

    # One-sided upper bound (Total Cholesterol)
    t_upper = TestResult(
        test_name="Total Cholesterol",
        value=248.0,
        unit="mg/dL",
        ref_high=200.0,
        flag=FlagStatus.HIGH,
    )
    html2 = render_range_gauge_html(t_upper)
    assert "Desirable: &lt; 200.0 mg/dL" in html2
    assert "248.0" in html2
    assert not any(line.startswith("    ") for line in html2.splitlines())

    # Non-numeric result (no range bar)
    t_non_numeric = TestResult(
        test_name="Urine Protein",
        value=None,
        raw_value="Trace",
        flag=FlagStatus.NORMAL,
    )
    assert render_range_gauge_html(t_non_numeric) == ""


def test_generate_audio_summary():
    """Verify that generate_audio_summary produces valid MP3 audio bytes when network is available, or gracefully handles offline mode."""
    from app import generate_audio_summary

    audio_en = generate_audio_summary("Lab report summary: all parameters normal.", lang="en")
    if audio_en is not None:
        assert len(audio_en) > 1000  # MP3 audio bytes

    audio_hi = generate_audio_summary("लैब रिपोर्ट सारांश: सभी परीक्षण सामान्य हैं।", lang="hi")
    if audio_hi is not None:
        assert len(audio_hi) > 1000
