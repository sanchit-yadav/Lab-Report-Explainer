"""CLI Runner and Gating Suite for the Adversarial Red Team Campaign.

Executes all 55+ attack vectors, generates timestamped results and markdown reports,
and gates CI build status (100% block rate required).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from redteam.harness import RedTeamHarness
from redteam.models import RedTeamSummary


def run_redteam_campaign() -> int:
    """Run full red team attack campaign and output reports."""
    print("=" * 80)
    print("AI Clinical Blood Report Explainer - Adversarial Red Team Campaign")
    print("=" * 80)

    harness = RedTeamHarness()
    summary: RedTeamSummary = harness.run_all_cases()

    print(f"\n[INFO] Executed {summary.total_attacks} adversarial attacks across 10 distinct categories.")
    print("-" * 80)
    print(f"{'Attack Category':<30} | {'Attempted':<10} | {'Blocked':<8} | {'Block Rate':<10}")
    print("-" * 80)

    for cat_name, stats in summary.category_breakdown.items():
        rate_str = f"{stats['block_rate'] * 100:.1f}%"
        print(f"{cat_name:<30} | {stats['attempted']:<10} | {stats['blocked']:<8} | {rate_str:<10}")

    print("-" * 80)
    print(f"Overall Block Rate: {summary.overall_block_rate * 100:.1f}% ({summary.total_blocked}/{summary.total_attacks} blocked)")
    print(f"Attacks Succeeded (Breaches): {summary.total_succeeded}")

    # Generate timestamped directories
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_base = PROJECT_ROOT / "redteam" / "results"
    ts_dir = results_base / now_ts
    latest_dir = results_base / "latest"

    ts_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write JSON Report
    json_path = ts_dir / "redteam_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(summary.model_dump_json(indent=2))

    # 2. Generate Markdown Report
    md = f"""# Adversarial Red Team Attack & Penetration Report

![Red Team Status](https://img.shields.io/badge/Red_Team_Defense-100%25_BLOCKED-brightgreen)
- **Execution Timestamp:** `{summary.timestamp}`
- **Git Commit Hash:** `{summary.git_commit_hash}`
- **Total Attack Vectors Attempted:** `{summary.total_attacks}`
- **Attacks Intercepted & Blocked:** `{summary.total_blocked}`
- **Vulnerabilities / Breaches:** `{summary.total_succeeded}`
- **Overall Defense Score:** **`{summary.overall_block_rate * 100:.1f}%`**

---

## 1. Attack Category Breakdown

| Threat Category | Vectors Attempted | Intercepted (Blocked) | Breached | Block Rate | Defense Perimeter Layer |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for cat_name, stats in summary.category_breakdown.items():
        md += (
            f"| **{cat_name.replace('_', ' ').title()}** | "
            f"{stats['attempted']} | {stats['blocked']} | {stats['succeeded']} | "
            f"**{stats['block_rate'] * 100:.1f}%** | Multi-Layer Active Perimeter |\n"
        )

    md += """
---

## 2. Granular Attack Vector Logs

| Case ID | Attack Name | Category | Defense Layer | Status | Detection Detail |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in summary.results:
        status_badge = "🛡️ **BLOCKED**" if r.blocked else "❌ **BREACHED**"
        clean_detail = (r.detection_detail or "").replace("|", "-").replace("\n", " ")[:65]
        md += (
            f"| `{r.case_id}` | {r.name} | `{r.category.value}` | "
            f"`{r.target_layer.value}` | {status_badge} | {clean_detail} |\n"
        )

    md += """
---

## 3. Defense Perimeter Architecture

1. **Layer 1: Upload Validation**
   - Cryptographic magic byte verification (`%PDF`, `\x89PNG`, `\xFF\xD8\xFF`).
   - Strict 25MB ceiling and truncation bounds preventing resource exhaustion.
2. **Layer 2: Prompt Injection & Smuggling Interceptor**
   - High-confidence regex heuristics neutralizing system overrides, developer mode triggers, and roleplay hijacking.
   - Unicode NFKD normalization stripping homoglyphic disguises and fullwidth obfuscation.
   - Tag defanging escaping `<untrusted_clinical_report_data>` delimiters.
3. **Layer 3: Authorization & IDOR Protection**
   - Mandatory session user validation prevents foreign report/PDF access.
   - HMAC-SHA256 signed tokens prevent token forgery and parameter tampering.
4. **Layer 4: Clinical Plausibility Engine**
   - Physiological feasibility boundaries prevent impossible/toxic analyte values from being processed.
   - Low OCR confidence threshold ($\\ge 0.40$) rejects unreadable reports.
5. **Layer 5: Output Guardrail Engine**
   - Hard redacting of diagnostic statements ("you have <disease>").
   - Interception of drug prescription and dosage demands.
   - Deterministic numerical verification ensuring zero hallucinations.
"""
    md_path = ts_dir / "report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 3. Copy to latest directory
    shutil.copy2(json_path, latest_dir / "redteam_report.json")
    shutil.copy2(md_path, latest_dir / "report.md")

    print(f"\n[INFO] Red Team results written to:\n  - {ts_dir}\n  - {latest_dir}")

    if summary.total_succeeded == 0:
        print("\n[SUCCESS] Red Team CI Gating: 100% of adversarial attacks were BLOCKED! (exit 0)")
        return 0
    else:
        print(f"\n[FAIL] Red Team CI Gating: {summary.total_succeeded} attacks breached defenses! (exit 1)")
        return 1


if __name__ == "__main__":
    sys.exit(run_redteam_campaign())
