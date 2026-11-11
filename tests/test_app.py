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
