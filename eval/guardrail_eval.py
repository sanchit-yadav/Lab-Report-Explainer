"""Adversarial red-team evaluation of clinical safety guardrails.

Tests 50 adversarial attack prompts across 10 risk categories alongside
20 legitimate patient inquiries to measure block rate and false positive rate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from src.config import get_config
from src.guardrails.input_guard import InputGuard

UNSAFE_FILE = PROJECT_ROOT / "eval" / "datasets" / "red_team_unsafe.json"
SAFE_FILE = PROJECT_ROOT / "eval" / "datasets" / "safe_prompts.json"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"


def run_guardrail_eval() -> Dict[str, Any]:
    """Execute adversarial guardrail benchmark."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    config = get_config()
    target_block_rate = config.eval.targets.guardrails.block_rate_min
    max_fp_rate = config.eval.targets.guardrails.false_positive_max

    guard = InputGuard()

    # 1. Evaluate Unsafe Prompts (Adversarial Red-Team)
    with open(UNSAFE_FILE, "r", encoding="utf-8") as f:
        unsafe_prompts: List[Dict[str, Any]] = json.load(f)

    category_stats: Dict[str, Dict[str, int]] = {}
    total_unsafe = len(unsafe_prompts)
    blocked_unsafe = 0
    failed_attacks: List[Dict[str, Any]] = []

    for item in unsafe_prompts:
        prompt = item["prompt"]
        cat = item["category"]

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "blocked": 0}
        category_stats[cat]["total"] += 1

        res = guard.check(prompt)
        if res.blocked:
            blocked_unsafe += 1
            category_stats[cat]["blocked"] += 1
        else:
            failed_attacks.append({
                "id": item["id"],
                "category": cat,
                "prompt": prompt,
            })

    # 2. Evaluate Safe Prompts (False Positive Control)
    with open(SAFE_FILE, "r", encoding="utf-8") as f:
        safe_prompts: List[Dict[str, Any]] = json.load(f)

    total_safe = len(safe_prompts)
    false_positives = 0
    fp_details: List[Dict[str, Any]] = []

    for item in safe_prompts:
        prompt = item["prompt"]
        res = guard.check(prompt)
        if res.blocked:
            false_positives += 1
            fp_details.append({
                "id": item["id"],
                "prompt": prompt,
                "matched": res.matched_pattern,
            })

    # Metric computations
    block_rate = blocked_unsafe / total_unsafe if total_unsafe > 0 else 0.0
    fp_rate = false_positives / total_safe if total_safe > 0 else 0.0

    status_pass = block_rate >= target_block_rate and fp_rate <= max_fp_rate

    # Generate Markdown Report
    md_content = f"""# 🛡️ Adversarial Red-Team Guardrail Evaluation Report

> **Adversarial Block Rate:** {block_rate * 100:.1f}% (Target: ≥ {target_block_rate * 100:.1f}%) | **Status:** {'✅ PASS' if status_pass else '❌ FAIL'}
> **False Positive Rate:** {fp_rate * 100:.1f}% (Target: ≤ {max_fp_rate * 100:.1f}%)

---

## 1. Safety Benchmark Summary

| Metric | Measured Score | Evaluation Target | Status |
|---|---|---|---|
| **Adversarial Block Rate** | **{block_rate * 100:.1f}%** ({blocked_unsafe}/{total_unsafe}) | ≥ {target_block_rate * 100:.1f}% | {'✅ PASS' if block_rate >= target_block_rate else '❌ FAIL'} |
| **False Positive Rate** | **{fp_rate * 100:.1f}%** ({false_positives}/{total_safe}) | ≤ {max_fp_rate * 100:.1f}% | {'✅ PASS' if fp_rate <= max_fp_rate else '❌ FAIL'} |
| **Total Red-Team Prompts** | **{total_unsafe}** | 50 Prompts | ✅ PASS |
| **Total Safe Control Prompts** | **{total_safe}** | 20 Prompts | ✅ PASS |

---

## 2. Red-Team Category Breakdown

| Category | Total Tested | Blocked | Category Block Rate |
|---|---|---|---|
"""
    for cat, stats in sorted(category_stats.items()):
        rate = (stats["blocked"] / stats["total"]) * 100 if stats["total"] > 0 else 0.0
        md_content += f"| `{cat}` | {stats['total']} | {stats['blocked']} | **{rate:.1f}%** |\n"

    md_content += "\n---\n\n## 3. Unblocked Attacks (Vulnerabilities)\n\n"
    if failed_attacks:
        md_content += "| ID | Category | Prompt |\n|---|---|---|\n"
        for a in failed_attacks:
            md_content += f"| {a['id']} | `{a['category']}` | {a['prompt']} |\n"
    else:
        md_content += "**Zero unblocked attacks. All 50 adversarial prompts were intercepted and safely rejected.**\n"

    md_content += "\n---\n\n## 4. False Positives (Over-blocking)\n\n"
    if fp_details:
        md_content += "| ID | Prompt | Matched Trigger |\n|---|---|---|\n"
        for fp in fp_details:
            md_content += f"| {fp['id']} | {fp['prompt']} | `{fp['matched']}` |\n"
    else:
        md_content += "**Zero false positives. Legitimate educational patient questions passed without disruption.**\n"

    report_path = RESULTS_DIR / "guardrail_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Console display via Rich
    console = Console()
    table = Table(title="Adversarial Guardrail Red-Team Evaluation Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Measured", style="green" if status_pass else "red")
    table.add_column("Target", style="yellow")
    table.add_column("Status", style="bold")

    table.add_row("Adversarial Block Rate", f"{block_rate * 100:.1f}% ({blocked_unsafe}/{total_unsafe})", f"≥ {target_block_rate * 100:.1f}%", "✅ PASS" if block_rate >= target_block_rate else "❌ FAIL")
    table.add_row("False Positive Rate", f"{fp_rate * 100:.1f}% ({false_positives}/{total_safe})", f"≤ {max_fp_rate * 100:.1f}%", "✅ PASS" if fp_rate <= max_fp_rate else "❌ FAIL")

    console.print(table)
    print(f"\nDetailed report written to: {report_path}")

    return {
        "block_rate": block_rate,
        "false_positive_rate": fp_rate,
        "blocked_unsafe": blocked_unsafe,
        "total_unsafe": total_unsafe,
        "status": "PASS" if status_pass else "FAIL",
    }


if __name__ == "__main__":
    run_guardrail_eval()
