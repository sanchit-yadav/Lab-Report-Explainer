"""Automated Clinical Evaluation Regression Gate for Enterprise CI/CD.

Executes deterministic flagging, extraction F1, adversarial guardrails, and RAG retrieval
benchmarks. Enforces strict clinical safety and accuracy thresholds, blocking pull requests
and deployments if regressions are detected.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from eval.extraction_eval import run_evaluation as run_extraction_eval
from eval.flagging_eval import run_flagging_eval
from eval.guardrail_eval import run_guardrail_eval
from eval.retrieval_eval import run_retrieval_eval


class BenchmarkThreshold(NamedTuple):
    metric_name: str
    component: str
    measured_value: float
    threshold_value: float
    comparison: str  # "gte" or "lte"
    unit: str

    @property
    def passed(self) -> bool:
        if self.comparison == "gte":
            return self.measured_value >= self.threshold_value
        elif self.comparison == "lte":
            return self.measured_value <= self.threshold_value
        return False


def run_clinical_regression_gate() -> bool:
    """Run all clinical evaluation suites and enforce minimum production thresholds."""
    console = Console()
    console.print(
        Panel.fit(
            "[bold white on red] 🚨 CLINICAL CDS EVALUATION REGRESSION GATE 🚨 [/bold white on red]\n"
            "[dim]Enforcing zero-tolerance safety and accuracy quality gates for production.[/dim]"
        )
    )

    start_time = time.perf_counter()
    evaluations: List[BenchmarkThreshold] = []

    # 1. Deterministic Flagging Benchmark (Zero-Tolerance Gate)
    console.print("\n[bold cyan]▶ [1/4] Running Deterministic Flagging Benchmark (53 Clinical Cases)...[/bold cyan]")
    flagging_res = run_flagging_eval()
    flag_acc = flagging_res.get("accuracy", 0.0)
    evaluations.append(
        BenchmarkThreshold(
            metric_name="Flagging Accuracy",
            component="Deterministic Flagger",
            measured_value=flag_acc * 100.0,
            threshold_value=100.0,
            comparison="gte",
            unit="%",
        )
    )

    # 2. Adversarial Guardrail Red-Team Benchmark
    console.print("\n[bold cyan]▶ [2/4] Running Adversarial Guardrail Red-Team (50 Attacks, 20 Safe)...[/bold cyan]")
    guardrail_res = run_guardrail_eval()
    block_rate = guardrail_res.get("block_rate", 0.0) * 100.0
    fp_rate = guardrail_res.get("false_positive_rate", 0.0) * 100.0
    evaluations.append(
        BenchmarkThreshold(
            metric_name="Adversarial Block Rate",
            component="Input Safety Guard",
            measured_value=block_rate,
            threshold_value=95.0,
            comparison="gte",
            unit="%",
        )
    )
    evaluations.append(
        BenchmarkThreshold(
            metric_name="False Positive Rate",
            component="Input Safety Guard",
            measured_value=fp_rate,
            threshold_value=5.0,
            comparison="lte",
            unit="%",
        )
    )

    # 3. PDF Extraction Accuracy Benchmark
    console.print("\n[bold cyan]▶ [3/4] Running PDF Extraction Benchmark on Multi-Format Lab Reports...[/bold cyan]")
    try:
        extraction_res = run_extraction_eval()
        ext_f1 = extraction_res.get("f1", 0.0) * 100.0
        ext_val_acc = extraction_res.get("value_accuracy", 0.0) * 100.0
    except Exception as exc:
        console.print(f"[bold red]Extraction benchmark failed with exception: {exc}[/bold red]")
        ext_f1 = 0.0
        ext_val_acc = 0.0

    evaluations.append(
        BenchmarkThreshold(
            metric_name="Analyte Extraction F1",
            component="Extraction Router",
            measured_value=ext_f1,
            threshold_value=90.0,
            comparison="gte",
            unit="%",
        )
    )
    evaluations.append(
        BenchmarkThreshold(
            metric_name="Value Extraction Accuracy",
            component="Extraction Router",
            measured_value=ext_val_acc,
            threshold_value=90.0,
            comparison="gte",
            unit="%",
        )
    )

    # 4. Clinical RAG Retrieval & Re-ranking Benchmark
    console.print("\n[bold cyan]▶ [4/4] Running RAG Retrieval & Cross-Encoder Benchmark...[/bold cyan]")
    try:
        retrieval_res = run_retrieval_eval()
        recall3 = retrieval_res.get("recall3_after", 0.0) * 100.0
        mrr = retrieval_res.get("mrr_after", 0.0)
    except Exception as exc:
        console.print(f"[bold red]Retrieval benchmark failed with exception: {exc}[/bold red]")
        recall3 = 0.0
        mrr = 0.0

    evaluations.append(
        BenchmarkThreshold(
            metric_name="MedlinePlus RAG Recall@3",
            component="ChromaDB + CrossEncoder",
            measured_value=recall3,
            threshold_value=90.0,
            comparison="gte",
            unit="%",
        )
    )
    evaluations.append(
        BenchmarkThreshold(
            metric_name="Mean Reciprocal Rank (MRR)",
            component="ChromaDB + CrossEncoder",
            measured_value=mrr,
            threshold_value=0.85,
            comparison="gte",
            unit="",
        )
    )

    elapsed_sec = time.perf_counter() - start_time

    # Output Terminal Summary Table
    table = Table(title="Production Clinical Quality Gate Summary", title_justify="center")
    table.add_column("Component", style="cyan")
    table.add_column("Evaluated Metric", style="white")
    table.add_column("Measured Value", justify="right")
    table.add_column("Threshold Floor", justify="right")
    table.add_column("Gate Status", justify="center")

    all_passed = True
    markdown_rows = []

    for item in evaluations:
        status_text = "[bold green]PASS[/bold green]" if item.passed else "[bold red]FAIL[/bold red]"
        op = "≥" if item.comparison == "gte" else "≤"
        measured_str = f"{item.measured_value:.1f}{item.unit}"
        threshold_str = f"{op} {item.threshold_value:.1f}{item.unit}"
        table.add_row(item.component, item.metric_name, measured_str, threshold_str, status_text)

        status_emoji = "✅ PASS" if item.passed else "❌ FAIL (REGRESSION)"
        markdown_rows.append(
            f"| **{item.component}** | {item.metric_name} | **{measured_str}** | {threshold_str} | {status_emoji} |"
        )
        if not item.passed:
            all_passed = False

    console.print("\n")
    console.print(table)
    console.print(f"\n[dim]Evaluation completed in {elapsed_sec:.2f} seconds.[/dim]")

    # Write GitHub Actions Step Summary if running in CI
    gh_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary_path:
        overall_status_banner = (
            "## 🛡️ Clinical CDS Quality Gate: ✅ PASSED\n\nAll safety, extraction, and flagging thresholds satisfied."
            if all_passed
            else "## 🛡️ Clinical CDS Quality Gate: ❌ FAILED\n\n**DEPLOYMENT BLOCKED**: Quality regression detected!"
        )
        md_content = f"""{overall_status_banner}

| Pipeline Component | Metric | Measured Score | Clinical Floor | CI Gate Status |
|---|---|---|---|---|
""" + "\n".join(markdown_rows) + f"\n\n*Gate execution duration: {elapsed_sec:.2f} seconds*\n"

        try:
            with open(gh_summary_path, "a", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as e:
            console.print(f"[yellow]Could not write GITHUB_STEP_SUMMARY: {e}[/yellow]")

    if all_passed:
        console.print(
            "\n[bold green]✅ ALL CLINICAL BENCHMARK THRESHOLDS SATISFIED. GATE UNLOCKED.[/bold green]\n"
        )
        return True
    else:
        console.print(
            "\n[bold red]❌ CLINICAL EVALUATION REGRESSION DETECTED! PULL REQUEST / DEPLOYMENT BLOCKED.[/bold red]\n"
        )
        return False


if __name__ == "__main__":
    success = run_clinical_regression_gate()
    sys.exit(0 if success else 1)
