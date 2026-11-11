"""Evaluation script for deterministic flagging accuracy.

Benchmarks the flagging engine across 50 diverse clinical scenarios,
including critical thresholds, inclusive boundaries, one-sided ranges,
and qualitative findings. Requires 100% accuracy.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from src.config import get_config
from src.extraction.schema import FlagStatus, TestResult
from src.flagging.flagger import Flagger

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"

BENCHMARK_CASES: List[Dict[str, Any]] = [
    # CBC
    {"name": "Hemoglobin Normal", "val": 14.5, "low": 13.0, "high": 17.0, "exp": FlagStatus.NORMAL},
    {"name": "Hemoglobin Lower Boundary", "val": 13.0, "low": 13.0, "high": 17.0, "exp": FlagStatus.NORMAL},
    {"name": "Hemoglobin Upper Boundary", "val": 17.0, "low": 13.0, "high": 17.0, "exp": FlagStatus.NORMAL},
    {"name": "Hemoglobin Low", "val": 11.2, "low": 13.0, "high": 17.0, "exp": FlagStatus.LOW},
    {"name": "Hemoglobin Critical Low", "val": 4.5, "low": 13.0, "high": 17.0, "exp": FlagStatus.CRITICAL_LOW},
    {"name": "Hemoglobin High", "val": 18.2, "low": 13.0, "high": 17.0, "exp": FlagStatus.HIGH},
    {"name": "Hemoglobin Critical High", "val": 26.0, "low": 13.0, "high": 17.0, "exp": FlagStatus.CRITICAL_HIGH},

    # WBC
    {"name": "WBC Normal", "val": 7500.0, "low": 4000.0, "high": 11000.0, "exp": FlagStatus.NORMAL},
    {"name": "WBC High", "val": 14500.0, "low": 4000.0, "high": 11000.0, "exp": FlagStatus.HIGH},
    {"name": "WBC Critical High", "val": 28000.0, "low": 4000.0, "high": 11000.0, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "WBC Low", "val": 3200.0, "low": 4000.0, "high": 11000.0, "exp": FlagStatus.LOW},
    {"name": "WBC Critical Low", "val": 1200.0, "low": 4000.0, "high": 11000.0, "exp": FlagStatus.CRITICAL_LOW},

    # Platelets
    {"name": "Platelets Normal", "val": 250000.0, "low": 150000.0, "high": 450000.0, "exp": FlagStatus.NORMAL},
    {"name": "Platelets Thrombocytopenia", "val": 85000.0, "low": 150000.0, "high": 450000.0, "exp": FlagStatus.LOW},
    {"name": "Platelets Critical Low", "val": 20000.0, "low": 150000.0, "high": 450000.0, "exp": FlagStatus.CRITICAL_LOW},

    # Lipids (one-sided ranges)
    {"name": "Cholesterol Normal (<200)", "val": 175.0, "low": None, "high": 200.0, "exp": FlagStatus.NORMAL},
    {"name": "Cholesterol Boundary", "val": 200.0, "low": None, "high": 200.0, "exp": FlagStatus.NORMAL},
    {"name": "Cholesterol High", "val": 245.0, "low": None, "high": 200.0, "exp": FlagStatus.HIGH},
    {"name": "Cholesterol Critical High", "val": 420.0, "low": None, "high": 200.0, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "Triglycerides Normal (<150)", "val": 110.0, "low": None, "high": 150.0, "exp": FlagStatus.NORMAL},
    {"name": "Triglycerides High", "val": 220.0, "low": None, "high": 150.0, "exp": FlagStatus.HIGH},
    {"name": "HDL Normal (>50)", "val": 62.0, "low": 50.0, "high": None, "exp": FlagStatus.NORMAL},
    {"name": "HDL Low", "val": 38.0, "low": 50.0, "high": None, "exp": FlagStatus.LOW},
    {"name": "HDL Critical Low", "val": 20.0, "low": 50.0, "high": None, "exp": FlagStatus.CRITICAL_LOW},

    # Thyroid
    {"name": "TSH Normal", "val": 2.1, "low": 0.45, "high": 4.5, "exp": FlagStatus.NORMAL},
    {"name": "TSH High", "val": 7.8, "low": 0.45, "high": 4.5, "exp": FlagStatus.HIGH},
    {"name": "TSH Critical High", "val": 14.5, "low": 0.45, "high": 4.5, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "TSH Low", "val": 0.30, "low": 0.45, "high": 4.5, "exp": FlagStatus.LOW},
    {"name": "TSH Critical Low", "val": 0.05, "low": 0.45, "high": 4.5, "exp": FlagStatus.CRITICAL_LOW},

    # Liver (LFT)
    {"name": "SGOT Normal", "val": 24.0, "low": 5.0, "high": 40.0, "exp": FlagStatus.NORMAL},
    {"name": "SGOT High", "val": 65.0, "low": 5.0, "high": 40.0, "exp": FlagStatus.HIGH},
    {"name": "SGOT Critical High", "val": 150.0, "low": 5.0, "high": 40.0, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "Bilirubin Normal", "val": 0.7, "low": 0.2, "high": 1.2, "exp": FlagStatus.NORMAL},
    {"name": "Bilirubin High", "val": 2.1, "low": 0.2, "high": 1.2, "exp": FlagStatus.HIGH},
    {"name": "Bilirubin Critical High", "val": 3.8, "low": 0.2, "high": 1.2, "exp": FlagStatus.CRITICAL_HIGH},

    # Kidney (KFT)
    {"name": "Creatinine Normal", "val": 0.9, "low": 0.6, "high": 1.2, "exp": FlagStatus.NORMAL},
    {"name": "Creatinine High", "val": 1.8, "low": 0.6, "high": 1.2, "exp": FlagStatus.HIGH},
    {"name": "Creatinine Critical High", "val": 3.2, "low": 0.6, "high": 1.2, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "eGFR Normal (>60)", "val": 90.0, "low": 60.0, "high": None, "exp": FlagStatus.NORMAL},
    {"name": "eGFR Low", "val": 45.0, "low": 60.0, "high": None, "exp": FlagStatus.LOW},
    {"name": "eGFR Critical Low", "val": 15.0, "low": 60.0, "high": None, "exp": FlagStatus.CRITICAL_LOW},

    # Diabetes
    {"name": "Fasting Glucose Normal", "val": 88.0, "low": 70.0, "high": 99.0, "exp": FlagStatus.NORMAL},
    {"name": "Fasting Glucose Impaired", "val": 115.0, "low": 70.0, "high": 99.0, "exp": FlagStatus.HIGH},
    {"name": "Fasting Glucose Critical High", "val": 240.0, "low": 70.0, "high": 99.0, "exp": FlagStatus.CRITICAL_HIGH},
    {"name": "HbA1c Normal", "val": 5.2, "low": 4.0, "high": 5.6, "exp": FlagStatus.NORMAL},
    {"name": "HbA1c High", "val": 7.5, "low": 4.0, "high": 5.6, "exp": FlagStatus.HIGH},
    {"name": "HbA1c Critical High", "val": 11.2, "low": 4.0, "high": 5.6, "exp": FlagStatus.CRITICAL_HIGH},

    # Non-Numeric Qualitative
    {"name": "HBsAg Positive", "raw": "Positive", "ref_raw": "Negative", "exp": FlagStatus.ABNORMAL},
    {"name": "HIV Reactive", "raw": "Reactive", "ref_raw": "Non-Reactive", "exp": FlagStatus.ABNORMAL},
    {"name": "Urine Ketones Negative", "raw": "Negative", "ref_raw": "Negative", "exp": FlagStatus.NORMAL},
    {"name": "VDRL Non-Reactive", "raw": "Non-Reactive", "ref_raw": "Non-Reactive", "exp": FlagStatus.NORMAL},
    {"name": "COVID Detected", "raw": "Detected", "ref_raw": "Not Detected", "exp": FlagStatus.ABNORMAL},

    # Missing Range
    {"name": "Missing Range Unknown", "val": 45.0, "low": None, "high": None, "exp": FlagStatus.UNKNOWN},
]


def run_flagging_eval() -> Dict[str, Any]:
    """Execute the deterministic flagging evaluation benchmark."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    config = get_config()
    req_accuracy = config.eval.targets.flagging.accuracy_required

    flagger = Flagger()
    total_cases = len(BENCHMARK_CASES)
    passed_cases = 0
    failures: List[Dict[str, Any]] = []

    category_counts: Dict[str, int] = {}

    for case in BENCHMARK_CASES:
        t = TestResult(
            test_name=case["name"],
            value=case.get("val"),
            raw_value=case.get("raw", str(case.get("val", ""))),
            ref_low=case.get("low"),
            ref_high=case.get("high"),
            ref_raw=case.get("ref_raw", ""),
        )
        assigned_flag = flagger.determine_flag(t)
        expected_flag = case["exp"]

        category_counts[assigned_flag.value] = category_counts.get(assigned_flag.value, 0) + 1

        if assigned_flag == expected_flag:
            passed_cases += 1
        else:
            failures.append({
                "case": case["name"],
                "expected": expected_flag.value,
                "assigned": assigned_flag.value,
            })

    accuracy = passed_cases / total_cases if total_cases > 0 else 0.0
    status_pass = accuracy >= req_accuracy

    # Generate Markdown Report
    md_content = f"""# 🏷️ Deterministic Flagging Evaluation Report

> **Target Accuracy:** {req_accuracy * 100:.1f}% (Required: 100% Deterministic) | **Status:** {'✅ PASS' if status_pass else '❌ FAIL'}

---

## 1. Summary Metrics

| Metric | Measured Score | Evaluation Target | Status |
|---|---|---|---|
| **Flagging Accuracy** | **{accuracy * 100:.1f}%** | 100.0% | {'✅ PASS' if status_pass else '❌ FAIL'} |
| **Total Benchmark Cases** | **{total_cases}** | ≥ 50 | ✅ PASS |
| **Cases Passed** | **{passed_cases}** | {total_cases} | {'✅' if passed_cases == total_cases else '❌'} |
| **Critical Multiplier Used** | **{config.extraction.flagging.critical_multiplier}x** | Config-Driven | ✅ PASS |

---

## 2. Flag Distribution Across Benchmark Cases

| Flag Category | Total Occurrences |
|---|---|
| `NORMAL` | {category_counts.get(FlagStatus.NORMAL.value, 0)} |
| `HIGH` | {category_counts.get(FlagStatus.HIGH.value, 0)} |
| `LOW` | {category_counts.get(FlagStatus.LOW.value, 0)} |
| `CRITICAL_HIGH` | {category_counts.get(FlagStatus.CRITICAL_HIGH.value, 0)} |
| `CRITICAL_LOW` | {category_counts.get(FlagStatus.CRITICAL_LOW.value, 0)} |
| `ABNORMAL` | {category_counts.get(FlagStatus.ABNORMAL.value, 0)} |
| `UNKNOWN` | {category_counts.get(FlagStatus.UNKNOWN.value, 0)} |

---

## 3. Discrepancies / Failures
"""
    if failures:
        md_content += "\n| Case Name | Expected Flag | Assigned Flag |\n|---|---|---|\n"
        for f in failures:
            md_content += f"| {f['case']} | `{f['expected']}` | `{f['assigned']}` |\n"
    else:
        md_content += "\n**Zero discrepancies observed. Deterministic logic matches clinical expectations with 100% precision.**\n"

    report_path = RESULTS_DIR / "flagging_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Console display via Rich
    console = Console()
    table = Table(title="Deterministic Flagging Evaluation Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Measured", style="green" if status_pass else "red")
    table.add_column("Target", style="yellow")
    table.add_column("Status", style="bold")

    table.add_row("Flagging Accuracy", f"{accuracy * 100:.1f}%", f"{req_accuracy * 100:.1f}%", "✅ PASS" if status_pass else "❌ FAIL")
    table.add_row("Benchmark Scenarios", str(total_cases), "≥ 50", "✅ PASS")
    table.add_row("Discrepancies", str(len(failures)), "0", "✅ PASS" if len(failures) == 0 else "❌ FAIL")

    console.print(table)
    print(f"\nDetailed report written to: {report_path}")

    return {
        "accuracy": accuracy,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "status": "PASS" if status_pass else "FAIL",
    }


if __name__ == "__main__":
    run_flagging_eval()
