"""Unit tests for the Clinical CDS Regression Gate."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from eval.regression_gate import BenchmarkThreshold, run_clinical_regression_gate


def test_benchmark_threshold_gte_and_lte():
    """Verify threshold comparison logic for greater-than-or-equal and less-than-or-equal."""
    # GTE passing
    t1 = BenchmarkThreshold("F1", "Extractor", 95.0, 90.0, "gte", "%")
    assert t1.passed is True

    # GTE failing
    t2 = BenchmarkThreshold("F1", "Extractor", 85.0, 90.0, "gte", "%")
    assert t2.passed is False

    # LTE passing
    t3 = BenchmarkThreshold("FP Rate", "Guard", 2.0, 5.0, "lte", "%")
    assert t3.passed is True

    # LTE failing
    t4 = BenchmarkThreshold("FP Rate", "Guard", 8.0, 5.0, "lte", "%")
    assert t4.passed is False


def test_regression_gate_passes_when_all_thresholds_met(tmp_path):
    """Verify regression gate returns True when all clinical benchmarks meet thresholds."""
    summary_file = tmp_path / "step_summary.md"

    with (
        patch("eval.regression_gate.run_flagging_eval") as mock_flag,
        patch("eval.regression_gate.run_guardrail_eval") as mock_guard,
        patch("eval.regression_gate.run_extraction_eval") as mock_ext,
        patch("eval.regression_gate.run_retrieval_eval") as mock_ret,
        patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}),
    ):
        mock_flag.return_value = {"accuracy": 1.0}
        mock_guard.return_value = {"block_rate": 0.98, "false_positive_rate": 0.02}
        mock_ext.return_value = {"f1": 0.96, "value_accuracy": 0.97}
        mock_ret.return_value = {"recall3_after": 0.95, "mrr_after": 0.92}

        result = run_clinical_regression_gate()
        assert result is True
        assert summary_file.exists()
        content = summary_file.read_text(encoding="utf-8")
        assert "Clinical CDS Quality Gate: ✅ PASSED" in content
        assert "Deterministic Flagger" in content


def test_regression_gate_blocks_on_flagging_regression():
    """Verify regression gate fails and blocks deployment if flagging accuracy drops below 100%."""
    with (
        patch("eval.regression_gate.run_flagging_eval") as mock_flag,
        patch("eval.regression_gate.run_guardrail_eval") as mock_guard,
        patch("eval.regression_gate.run_extraction_eval") as mock_ext,
        patch("eval.regression_gate.run_retrieval_eval") as mock_ret,
    ):
        # 98% accuracy (single misclassification in clinical range)
        mock_flag.return_value = {"accuracy": 0.98}
        mock_guard.return_value = {"block_rate": 0.98, "false_positive_rate": 0.02}
        mock_ext.return_value = {"f1": 0.96, "value_accuracy": 0.97}
        mock_ret.return_value = {"recall3_after": 0.95, "mrr_after": 0.92}

        result = run_clinical_regression_gate()
        assert result is False
