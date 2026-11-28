"""Evaluation script for scanned report extraction across synthetic fixtures.

Computes real, unestimated benchmark metrics:
- Field-level Precision, Recall, and F1
- Numeric Exact-Match Accuracy
- Unit Extraction Accuracy
- Deterministic Flag Accuracy
- Critical Error Count (wrong number or flag)
- Per-condition performance breakdown

Outputs real numbers to /evals/results/<timestamp>/ with git commit hash and model names.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on Python sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.extraction.router import ExtractionRouter
from src.extraction.schema import FlagStatus

FIXTURES_DIR = Path("tests/fixtures/scanned")
RESULTS_ROOT = Path("evals/results")


def get_git_commit_hash() -> str:
    """Retrieve the current Git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def normalize_name(name: str) -> str:
    """Canonicalize analyte name for robust fuzzy matching."""
    s = name.lower().replace("-", " ").replace("_", " ").strip()
    synonyms = {
        "white blood cell count": "wbc",
        "white blood cells": "wbc",
        "wbc count": "wbc",
        "platelet count": "platelets",
        "fasting blood glucose": "glucose",
        "fasting glucose": "glucose",
        "serum creatinine": "creatinine",
        "blood urea nitrogen": "bun",
        "serum calcium": "calcium",
        "total protein": "protein",
        "free t4": "ft4",
        "total t3": "t3",
    }
    return synonyms.get(s, s)


def normalize_unit(unit: str) -> str:
    """Normalize unit string for comparison."""
    u = unit.lower().replace(" ", "").strip()
    mapping = {
        "10^3/ul": "10^3/ul",
        "x10^3/ul": "10^3/ul",
        "k/ul": "10^3/ul",
        "cells/cumm": "10^3/ul",
        "mg/dl": "mg/dl",
        "g/dl": "g/dl",
        "mmol/l": "mmol/l",
        "u/l": "u/l",
        "uiu/ml": "uiu/ml",
        "miu/l": "uiu/ml",
        "ng/dl": "ng/dl",
        "%": "%",
    }
    return mapping.get(u, u)


def evaluate_all_scanned_fixtures() -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    git_hash = get_git_commit_hash()
    router = ExtractionRouter()

    fixture_files = [
        ("scanned_clean.pdf", "image_only_pdf"),
        ("scanned_noisy.png", "photographed_noisy"),
        ("scanned_rotated.png", "rotated_90_deg"),
        ("scanned_skewed.png", "skewed_7_deg"),
        ("scanned_lowres.png", "low_resolution_downsampled"),
        ("scanned_multipage.pdf", "multipage_image_only_pdf"),
    ]

    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_numeric_matches = 0
    total_unit_matches = 0
    total_flag_matches = 0
    total_critical_errors = 0
    total_gt_tests = 0

    per_condition_results: List[Dict[str, Any]] = []

    print("\n========================================================")
    print(f"RUNNING SCANNED EXTRACTION BENCHMARK ({timestamp})")
    print(f"Git Commit: {git_hash}")
    print(f"Model: {router.tier3.config.models.vision_fallback}")
    print("========================================================\n")

    for filename, condition in fixture_files:
        file_path = FIXTURES_DIR / filename
        gt_path = FIXTURES_DIR / (Path(filename).stem + ".json")

        if not file_path.exists() or not gt_path.exists():
            print(f"Skipping {filename}: file or ground truth JSON missing.")
            continue

        with open(gt_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)

        gt_tests = gt_data.get("tests", [])
        total_gt_tests += len(gt_tests)

        t0 = time.time()
        file_bytes = file_path.read_bytes()
        extracted_report = router.extract(file_bytes)
        elapsed_sec = round(time.time() - t0, 2)

        # Match extracted tests against ground truth
        matched_gt_indices = set()
        cond_numeric_matches = 0
        cond_unit_matches = 0
        cond_flag_matches = 0
        cond_critical_errors = 0
        cond_tp = 0

        for ext_test in extracted_report.tests:
            ext_norm = normalize_name(ext_test.test_name)
            match_idx = None
            for idx, gt in enumerate(gt_tests):
                if idx in matched_gt_indices:
                    continue
                if normalize_name(gt["test_name"]) == ext_norm or ext_norm in normalize_name(
                    gt["test_name"]
                ):
                    match_idx = idx
                    break

            if match_idx is not None:
                matched_gt_indices.add(match_idx)
                cond_tp += 1
                gt = gt_tests[match_idx]

                # Check numeric value exact match
                if ext_test.value is not None and gt["value"] is not None:
                    if abs(ext_test.value - gt["value"]) < 1e-3:
                        cond_numeric_matches += 1
                    else:
                        cond_critical_errors += 1
                        print(
                            f"  [CRITICAL VALUE MISMATCH] {ext_test.test_name}: got {ext_test.value}, expected {gt['value']}"
                        )

                # Check unit
                if normalize_unit(ext_test.unit) == normalize_unit(gt["unit"]):
                    cond_unit_matches += 1

                # Check flag
                ext_flag = (
                    ext_test.flag.value
                    if isinstance(ext_test.flag, FlagStatus)
                    else str(ext_test.flag).lower()
                )
                gt_flag = gt["flag"].lower()
                if ext_flag == gt_flag:
                    cond_flag_matches += 1
                else:
                    cond_critical_errors += 1
                    print(
                        f"  [CRITICAL FLAG MISMATCH] {ext_test.test_name}: got {ext_flag}, expected {gt_flag}"
                    )

        cond_fp = len(extracted_report.tests) - cond_tp
        cond_fn = len(gt_tests) - cond_tp

        total_tp += cond_tp
        total_fp += cond_fp
        total_fn += cond_fn
        total_numeric_matches += cond_numeric_matches
        total_unit_matches += cond_unit_matches
        total_flag_matches += cond_flag_matches
        total_critical_errors += cond_critical_errors

        cond_precision = cond_tp / (cond_tp + cond_fp) if (cond_tp + cond_fp) > 0 else 0.0
        cond_recall = cond_tp / len(gt_tests) if len(gt_tests) > 0 else 0.0
        cond_f1 = (
            (2 * cond_precision * cond_recall) / (cond_precision + cond_recall)
            if (cond_precision + cond_recall) > 0
            else 0.0
        )

        per_condition_results.append(
            {
                "fixture": filename,
                "condition": condition,
                "ground_truth_tests": len(gt_tests),
                "extracted_tests": len(extracted_report.tests),
                "tp": cond_tp,
                "fp": cond_fp,
                "fn": cond_fn,
                "precision": round(cond_precision, 4),
                "recall": round(cond_recall, 4),
                "f1": round(cond_f1, 4),
                "numeric_exact_match_pct": round((cond_numeric_matches / len(gt_tests)) * 100, 2)
                if len(gt_tests) > 0
                else 0.0,
                "unit_accuracy_pct": round((cond_unit_matches / len(gt_tests)) * 100, 2)
                if len(gt_tests) > 0
                else 0.0,
                "flag_accuracy_pct": round((cond_flag_matches / len(gt_tests)) * 100, 2)
                if len(gt_tests) > 0
                else 0.0,
                "critical_errors": cond_critical_errors,
                "latency_seconds": elapsed_sec,
            }
        )

        print(
            f"[{condition}] {filename}: {cond_tp}/{len(gt_tests)} matched | F1: {cond_f1:.2f} | Num Match: {cond_numeric_matches}/{len(gt_tests)} | Latency: {elapsed_sec}s"
        )

    # Aggregate metrics
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_recall = total_tp / total_gt_tests if total_gt_tests > 0 else 0.0
    overall_f1 = (
        (2 * overall_precision * overall_recall) / (overall_precision + overall_recall)
        if (overall_precision + overall_recall) > 0
        else 0.0
    )
    numeric_exact_match_pct = (
        (total_numeric_matches / total_gt_tests) * 100 if total_gt_tests > 0 else 0.0
    )
    unit_accuracy_pct = (total_unit_matches / total_gt_tests) * 100 if total_gt_tests > 0 else 0.0
    flag_accuracy_pct = (total_flag_matches / total_gt_tests) * 100 if total_gt_tests > 0 else 0.0

    eval_summary = {
        "timestamp": timestamp,
        "git_commit": git_hash,
        "models": {
            "vision_fallback": router.tier3.config.models.vision_fallback,
            "flagger": "deterministic_pure_code",
        },
        "aggregate_metrics": {
            "total_ground_truth_tests": total_gt_tests,
            "total_extracted_tests": total_tp + total_fp,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "precision": round(overall_precision, 4),
            "recall": round(overall_recall, 4),
            "f1_score": round(overall_f1, 4),
            "numeric_exact_match_pct": round(numeric_exact_match_pct, 2),
            "unit_accuracy_pct": round(unit_accuracy_pct, 2),
            "flag_accuracy_pct": round(flag_accuracy_pct, 2),
            "critical_error_count": total_critical_errors,
        },
        "per_condition_breakdown": per_condition_results,
    }

    # Save JSON results
    json_path = output_dir / "scanned_extraction_eval.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2)

    # Save Markdown report
    md_path = output_dir / "scanned_extraction_eval.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Scanned Report Extraction Benchmark Results\n\n")
        f.write(f"- **Timestamp:** `{timestamp}`\n")
        f.write(f"- **Git Commit Hash:** `{git_hash}`\n")
        f.write(f"- **Multimodal Vision Model:** `{router.tier3.config.models.vision_fallback}`\n")
        f.write("- **Flagging Engine:** `Flagger (Deterministic Python Mathematical Interval)`\n\n")
        f.write("## Summary Metrics\n\n")
        f.write("| Metric | Result |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| **Field-Level Precision** | {overall_precision * 100:.2f}% |\n")
        f.write(f"| **Field-Level Recall** | {overall_recall * 100:.2f}% |\n")
        f.write(f"| **Field-Level F1 Score** | {overall_f1:.4f} |\n")
        f.write(
            f"| **Numeric Exact-Match Accuracy** | {numeric_exact_match_pct:.2f}% ({total_numeric_matches}/{total_gt_tests}) |\n"
        )
        f.write(
            f"| **Unit Extraction Accuracy** | {unit_accuracy_pct:.2f}% ({total_unit_matches}/{total_gt_tests}) |\n"
        )
        f.write(
            f"| **Deterministic Flag Accuracy** | {flag_accuracy_pct:.2f}% ({total_flag_matches}/{total_gt_tests}) |\n"
        )
        f.write(
            f"| **Critical Clinical Errors** | **{total_critical_errors}** (wrong number or flag) |\n\n"
        )
        f.write("## Per-Condition Performance Breakdown\n\n")
        f.write(
            "| Condition | Fixture | GT Tests | Extracted | F1 | Numeric Match | Flag Accuracy | Critical Errors | Latency |\n"
        )
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for c in per_condition_results:
            f.write(
                f"| `{c['condition']}` | `{c['fixture']}` | {c['ground_truth_tests']} | {c['extracted_tests']} | {c['f1']:.2f} | {c['numeric_exact_match_pct']}% | {c['flag_accuracy_pct']}% | {c['critical_errors']} | {c['latency_seconds']}s |\n"
            )

    print("\nSaved evaluation results to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}\n")

    return eval_summary


if __name__ == "__main__":
    evaluate_all_scanned_fixtures()
