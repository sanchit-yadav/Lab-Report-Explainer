"""CLI utility to convert any failing test or edge-case report into a permanent regression test.

Usage:
    python -m evals.add_regression <path/to/report_file> --ground-truth <path/to/gt.json> --reason "Missed mmol/L unit" --issue "GH-142"
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Dict


def get_next_regression_id(regression_dir: Path) -> str:
    """Find the next available reg_XXX identifier."""
    existing = list(regression_dir.glob("reg_*.json"))
    max_idx = 0
    for p in existing:
        stem = p.stem  # e.g. reg_008
        parts = stem.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            max_idx = max(max_idx, int(parts[1]))
    next_idx = max_idx + 1
    return f"reg_{next_idx:03d}"


def add_regression_case(
    report_path: Path,
    ground_truth_path: Optional[Path],
    reason: str,
    issue_reference: str = "",
    fixed_by: str = "",
) -> Path:
    """Add report file and ground-truth JSON to evals/golden/regression/."""
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    regression_dir = Path(__file__).resolve().parent / "golden" / "regression"
    regression_dir.mkdir(parents=True, exist_ok=True)

    case_id = get_next_regression_id(regression_dir)
    ext = report_path.suffix.lower()
    dest_report = regression_dir / f"{case_id}{ext}"
    dest_json = regression_dir / f"{case_id}.json"

    # Copy report binary
    shutil.copy2(report_path, dest_report)

    # Load or generate ground truth
    gt_data: Dict[str, Any] = {}
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
    else:
        gt_data = {
            "case_id": case_id,
            "patient_name": "Regression Test Patient",
            "patient_age": "45",
            "patient_gender": "Unknown",
            "lab_name": "Regression Lab",
            "layout": "regression",
            "variation": "bug_fix",
            "tests": [],
        }

    gt_data["case_id"] = case_id
    gt_data["regression_metadata"] = {
        "added_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reason": reason,
        "issue_reference": issue_reference,
        "fixed_by": fixed_by,
        "original_filename": report_path.name,
    }

    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(gt_data, f, indent=2)

    print(f"[SUCCESS] Added permanent regression case {case_id}:")
    print(f"  Report: {dest_report}")
    print(f"  Ground Truth: {dest_json}")
    print(f"  Reason: {reason}")
    return dest_json


def main():
    parser = argparse.ArgumentParser(description="Add permanent regression test case to golden dataset.")
    parser.add_argument("report_file", type=Path, help="Path to failing report file (PDF or image)")
    parser.add_argument("--ground-truth", "-g", type=Path, default=None, help="Path to companion ground truth JSON")
    parser.add_argument("--reason", "-r", required=True, help="Detailed explanation of the failure or bug")
    parser.add_argument("--issue", "-i", default="", help="Issue reference (e.g. GH-42 or Bug-12)")
    parser.add_argument("--author", "-a", default="CI / Pipeline Engineer", help="Author adding regression")

    args = parser.parse_args()
    try:
        add_regression_case(
            report_path=args.report_file,
            ground_truth_path=args.ground_truth,
            reason=args.reason,
            issue_reference=args.issue,
            fixed_by=args.author,
        )
    except Exception as e:
        print(f"[ERROR] Failed to add regression case: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
