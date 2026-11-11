"""Evaluation script for PDF Extraction accuracy.

Compares extracted results against labeled ground-truth JSON files.
Computes precision, recall, and F1 at the analyte and field level,
and outputs a comprehensive markdown report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from src.config import get_config
from src.extraction.router import ExtractionRouter
from src.extraction.schema import LabReport, TestResult

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_reports"
LABELED_DIR = PROJECT_ROOT / "data" / "labeled"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"


def normalize_name(name: str) -> str:
    """Normalize test name for resilient matching."""
    return "".join(c.lower() for c in name if c.isalnum())


def evaluate_report(
    extracted: LabReport, ground_truth: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare an extracted LabReport against ground-truth data."""
    gt_tests: List[Dict[str, Any]] = ground_truth.get("tests", [])
    extracted_tests: List[TestResult] = extracted.tests

    # Index ground truth tests by normalized test name
    gt_map = {normalize_name(t["test_name"]): t for t in gt_tests}
    ext_map = {normalize_name(t.test_name): t for t in extracted_tests}

    # Matches
    matched_names = set(gt_map.keys()) & set(ext_map.keys())
    missing_names = set(gt_map.keys()) - set(ext_map.keys())
    extra_names = set(ext_map.keys()) - set(gt_map.keys())

    value_correct = 0
    unit_correct = 0
    range_correct = 0

    for name_key in matched_names:
        gt = gt_map[name_key]
        ext = ext_map[name_key]

        # Check value match (handle numeric tolerance or string match)
        if gt["value"] is None and ext.value is None:
            # Both non-numeric
            if gt.get("raw_value", "").strip().lower() == ext.raw_value.strip().lower():
                value_correct += 1
        elif gt["value"] is not None and ext.value is not None:
            if abs(gt["value"] - ext.value) < 1e-3:
                value_correct += 1

        # Check unit match
        gt_unit = (gt.get("unit") or "").strip().lower()
        ext_unit = (ext.unit or "").strip().lower()
        if gt_unit == ext_unit or (not gt_unit and not ext_unit):
            unit_correct += 1

        # Check reference range match
        low_match = (gt.get("ref_low") is None and ext.ref_low is None) or (
            gt.get("ref_low") is not None
            and ext.ref_low is not None
            and abs(gt["ref_low"] - ext.ref_low) < 1e-3
        )
        high_match = (gt.get("ref_high") is None and ext.ref_high is None) or (
            gt.get("ref_high") is not None
            and ext.ref_high is not None
            and abs(gt["ref_high"] - ext.ref_high) < 1e-3
        )
        if low_match and high_match:
            range_correct += 1

    total_gt = len(gt_tests)
    total_ext = len(extracted_tests)
    matched_count = len(matched_names)

    return {
        "total_gt": total_gt,
        "total_ext": total_ext,
        "matched_count": matched_count,
        "missing_count": len(missing_names),
        "extra_count": len(extra_names),
        "value_correct": value_correct,
        "unit_correct": unit_correct,
        "range_correct": range_correct,
        "extraction_method": extracted.extraction_method,
    }


def run_evaluation() -> Dict[str, Any]:
    """Run extraction evaluation on all sample reports."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    config = get_config()
    target_f1 = config.eval.targets.extraction.f1_min

    router = ExtractionRouter()
    report_files = sorted(SAMPLE_DIR.glob("*.pdf"))

    total_gt_all = 0
    total_ext_all = 0
    matched_all = 0
    value_correct_all = 0
    unit_correct_all = 0
    range_correct_all = 0

    per_report_results: List[Dict[str, Any]] = []

    for pdf_path in report_files:
        json_path = LABELED_DIR / f"{pdf_path.stem}.json"
        if not json_path.exists():
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)

        extracted = router.extract(pdf_path)
        eval_metrics = evaluate_report(extracted, gt_data)
        eval_metrics["filename"] = pdf_path.name
        per_report_results.append(eval_metrics)

        total_gt_all += eval_metrics["total_gt"]
        total_ext_all += eval_metrics["total_ext"]
        matched_all += eval_metrics["matched_count"]
        value_correct_all += eval_metrics["value_correct"]
        unit_correct_all += eval_metrics["unit_correct"]
        range_correct_all += eval_metrics["range_correct"]

    # Precision, Recall, F1 for analyte identification
    precision = matched_all / total_ext_all if total_ext_all > 0 else 0.0
    recall = matched_all / total_gt_all if total_gt_all > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # Field accuracies relative to matched analytes
    value_acc = value_correct_all / matched_all if matched_all > 0 else 0.0
    unit_acc = unit_correct_all / matched_all if matched_all > 0 else 0.0
    range_acc = range_correct_all / matched_all if matched_all > 0 else 0.0

    summary = {
        "total_reports": len(per_report_results),
        "total_ground_truth_fields": total_gt_all,
        "total_extracted_fields": total_ext_all,
        "matched_analytes": matched_all,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "value_accuracy": value_acc,
        "unit_accuracy": unit_acc,
        "range_accuracy": range_acc,
        "target_f1": target_f1,
        "status": "PASS" if f1 >= target_f1 else "FAIL",
    }

    # Generate Markdown Report
    md_content = f"""# 📊 PDF Extraction Evaluation Report

> **Target F1:** ≥ {target_f1 * 100:.1f}% | **Status:** {'✅ PASS' if f1 >= target_f1 else '❌ FAIL'}

---

## 1. Overall Performance Metrics

| Metric | Measured Score | Evaluation Target | Status |
|---|---|---|---|
| **Analyte F1 Score** | **{f1 * 100:.1f}%** | ≥ {target_f1 * 100:.1f}% | {'✅ PASS' if f1 >= target_f1 else '❌ FAIL'} |
| **Analyte Precision** | **{precision * 100:.1f}%** | ≥ 95.0% | {'✅' if precision >= 0.95 else '⚠️'} |
| **Analyte Recall** | **{recall * 100:.1f}%** | ≥ 90.0% | {'✅' if recall >= 0.90 else '⚠️'} |
| **Value Accuracy** | **{value_acc * 100:.1f}%** | ≥ 95.0% | {'✅' if value_acc >= 0.95 else '⚠️'} |
| **Unit Accuracy** | **{unit_acc * 100:.1f}%** | ≥ 90.0% | {'✅' if unit_acc >= 0.90 else '⚠️'} |
| **Reference Range Accuracy** | **{range_acc * 100:.1f}%** | ≥ 85.0% | {'✅' if range_acc >= 0.85 else '⚠️'} |

---

## 2. Per-Report Breakdown

| Report File | Extractor Used | Ground Truth | Extracted | Matched | Value Acc | Range Acc |
|---|---|---|---|---|---|---|
"""
    for r in per_report_results:
        v_rate = f"{(r['value_correct'] / r['matched_count']) * 100:.0f}%" if r["matched_count"] > 0 else "0%"
        rg_rate = f"{(r['range_correct'] / r['matched_count']) * 100:.0f}%" if r["matched_count"] > 0 else "0%"
        md_content += f"| `{r['filename']}` | `{r['extraction_method']}` | {r['total_gt']} | {r['total_ext']} | {r['matched_count']} | {v_rate} | {rg_rate} |\n"

    report_md_path = RESULTS_DIR / "extraction_report.md"
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Print Console Summary via Rich
    console = Console()
    table = Table(title="PDF Extraction Evaluation Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Measured", style="green" if f1 >= target_f1 else "red")
    table.add_column("Target", style="yellow")
    table.add_column("Status", style="bold")

    table.add_row("Extraction F1", f"{f1 * 100:.1f}%", f"≥ {target_f1 * 100:.1f}%", "✅ PASS" if f1 >= target_f1 else "❌ FAIL")
    table.add_row("Precision", f"{precision * 100:.1f}%", "≥ 95.0%", "✅ PASS" if precision >= 0.95 else "⚠️")
    table.add_row("Recall", f"{recall * 100:.1f}%", "≥ 90.0%", "✅ PASS" if recall >= 0.90 else "⚠️")
    table.add_row("Value Accuracy", f"{value_acc * 100:.1f}%", "≥ 95.0%", "✅ PASS" if value_acc >= 0.95 else "⚠️")
    table.add_row("Unit Accuracy", f"{unit_acc * 100:.1f}%", "≥ 90.0%", "✅ PASS" if unit_acc >= 0.90 else "⚠️")
    table.add_row("Range Accuracy", f"{range_acc * 100:.1f}%", "≥ 85.0%", "✅ PASS" if range_acc >= 0.85 else "⚠️")

    console.print(table)
    print(f"\nDetailed report written to: {report_md_path}")
    return summary


if __name__ == "__main__":
    run_evaluation()
