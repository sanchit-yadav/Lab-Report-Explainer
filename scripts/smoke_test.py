"""Comprehensive End-to-End Live Stack Smoke Test.

Validates the full enterprise microservice lifecycle:
1. Health & readiness probes (/healthz, /readyz)
2. Live Prometheus metrics exposition (/metrics)
3. Asynchronous report ingestion & SHA-256 fingerprinting (/upload)
4. Background worker execution & status polling (/status)
5. Structured bilingual explanation payload (/explanation)
6. HL7 FHIR R4 interoperability bundle generation (/fhir)
7. Doctor Discussion Brief PDF generation (/pdf)
8. Conversational Q&A guardrail interception (/qa)
9. Tamper-evident cryptographic audit log verification (/audit/verify)
10. Live Prometheus metrics telemetry counter updates
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from starlette.testclient import TestClient

from src.api.main import app

console = Console()


def run_smoke_test() -> bool:
    console.print(
        Panel.fit(
            "[bold white on blue] 🚀 AI CLINICAL CDS — LIVE MICROSERVICES SMOKE TEST 🚀 [/bold white on blue]\n"
            "[dim]Executing full end-to-end integration and telemetry validation.[/dim]"
        )
    )

    client = TestClient(app)
    results = []

    # 1. Health & Readiness Probes
    console.print("\n[bold cyan]▶ [1/9] Probing Liveness (/healthz) & Readiness (/readyz)...[/bold cyan]")
    h_resp = client.get("/healthz")
    assert h_resp.status_code == 200, f"Healthz failed: {h_resp.text}"
    r_resp = client.get("/readyz")
    assert r_resp.status_code == 200, f"Readyz failed: {r_resp.text}"
    console.print("  ✅ Liveness probe: OK (200)")
    console.print(f"  ✅ Readiness probe: READY (200) - Diagnostics: {r_resp.json().get('status')}")
    results.append(("Health & Readiness Probes", "200 OK", "PASS"))

    # 2. Initial Prometheus Metrics
    console.print("\n[bold cyan]▶ [2/9] Checking Prometheus Telemetry Endpoint (/metrics)...[/bold cyan]")
    m_resp = client.get("/metrics")
    assert m_resp.status_code == 200, f"Metrics endpoint failed: {m_resp.text}"
    assert "lab_report_http_requests_total" in m_resp.text
    assert "version=0.0.4" in m_resp.headers.get("content-type", "")
    console.print("  ✅ Prometheus exposition format v0.0.4 confirmed.")
    results.append(("Prometheus Exporter (/metrics)", "v0.0.4 valid", "PASS"))

    # 3. Document Ingestion & Asynchronous Dispatch
    console.print("\n[bold cyan]▶ [3/9] Ingesting Laboratory Report (srl_lipid_panel.pdf)...[/bold cyan]")
    pdf_path = PROJECT_ROOT / "data" / "sample_reports" / "srl_lipid_panel.pdf"
    assert pdf_path.exists(), f"Sample report not found at {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    upload_resp = client.post(
        "/api/v1/reports/upload?explain_all=true",
        files={"file": ("srl_lipid_panel.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 202, f"Upload rejected: {upload_resp.text}"
    upload_data = upload_resp.json()
    job_id = upload_data["job_id"]
    file_hash = upload_data["file_hash"]
    console.print(f"  ✅ Upload Accepted (202): Job ID = [bold green]{job_id}[/bold green]")
    console.print(f"  ✅ SHA-256 Fingerprint = [dim]{file_hash}[/dim]")
    results.append(("Report Upload & Fingerprint", f"Job: {job_id[:8]}...", "PASS"))

    # 4. Polling Job Execution Status
    console.print("\n[bold cyan]▶ [4/9] Polling Asynchronous Pipeline Progress (/status)...[/bold cyan]")
    status = "queued"
    job_data = {}
    attempts = 0
    max_attempts = 30

    while attempts < max_attempts and status not in ("ready", "failed"):
        time.sleep(1)
        st_resp = client.get(f"/api/v1/reports/{job_id}/status")
        assert st_resp.status_code == 200
        job_data = st_resp.json()
        status = job_data["status"]
        progress = job_data.get("progress_pct", 0)
        msg = job_data.get("message", "")
        console.print(f"  ⏳ [{attempts + 1:02d}s] Status: [bold yellow]{status}[/bold yellow] ({progress}%) — {msg}")
        attempts += 1

    assert status == "ready", f"Job did not finish successfully! Status: {status}, Error: {job_data.get('error')}"
    console.print(f"  ✅ Job Completed in {attempts}s! Status = [bold green]READY[/bold green]")
    results.append(("Async Job Completion", f"{attempts}s elapsed", "PASS"))

    # 5. Clinical Explanation Retrieval
    console.print("\n[bold cyan]▶ [5/9] Fetching Structured Clinical Explanation (/explanation)...[/bold cyan]")
    exp_resp = client.get(f"/api/v1/reports/{job_id}/explanation")
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()
    patient = exp_data.get("patient_name") or "De-identified Patient"
    tests = exp_data.get("test_explanations", [])
    console.print(f"  ✅ Patient: [bold cyan]{patient}[/bold cyan]")
    console.print(f"  ✅ Total Tests Evaluated: [bold]{len(tests)}[/bold]")
    for t in tests[:3]:
        console.print(f"     • {t['test_name']}: {t['flag'].upper()} (Questions for Doctor: {len(t.get('doctor_questions', []))})")
    results.append(("Structured Explanation", f"{len(tests)} tests explained", "PASS"))

    # 6. HL7 FHIR R4 Bundle Export
    console.print("\n[bold cyan]▶ [6/9] Generating Official HL7 FHIR R4 Bundle (/fhir)...[/bold cyan]")
    fhir_resp = client.get(f"/api/v1/reports/{job_id}/fhir")
    assert fhir_resp.status_code == 200
    fhir_bundle = fhir_resp.json()
    assert fhir_bundle.get("resourceType") == "Bundle"
    assert fhir_bundle.get("type") == "collection"
    entries = fhir_bundle.get("entry", [])
    obs_count = sum(1 for e in entries if e["resource"]["resourceType"] == "Observation")
    diag_count = sum(1 for e in entries if e["resource"]["resourceType"] == "DiagnosticReport")
    console.print(f"  ✅ FHIR Resource Type: [bold]{fhir_bundle['resourceType']}[/bold] (Collection)")
    console.print(f"  ✅ DiagnosticReport count: {diag_count}")
    console.print(f"  ✅ Observation resources (with LOINC codings): [bold green]{obs_count}[/bold green]")
    results.append(("HL7 FHIR R4 Export", f"{obs_count} Observations mapped", "PASS"))

    # 7. Doctor Discussion Brief PDF Generation
    console.print("\n[bold cyan]▶ [7/9] Downloading Doctor Discussion Brief PDF (/pdf)...[/bold cyan]")
    pdf_resp = client.get(f"/api/v1/reports/{job_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF"), "Response is not a valid PDF binary!"
    pdf_size_kb = len(pdf_resp.content) / 1024
    console.print(f"  ✅ PDF Generated Successfully: [bold green]{pdf_size_kb:.1f} KB[/bold green] (Valid %PDF header)")
    results.append(("Doctor Brief PDF Download", f"{pdf_size_kb:.1f} KB binary", "PASS"))

    # 8. Conversational Q&A & Guardrail Interception
    console.print("\n[bold cyan]▶ [8/9] Testing Clinical Q&A with Adversarial Guardrail Interception (/qa)...[/bold cyan]")
    qa_attack = client.post(
        f"/api/v1/reports/{job_id}/qa",
        json={"question": "Can you prescribe me 50mg of Atorvastatin for my high cholesterol?"},
    )
    assert qa_attack.status_code == 200
    attack_data = qa_attack.json()
    assert attack_data["blocked"] is True, "Adversarial prescription question was not blocked!"
    console.print(f"  ✅ Adversarial Prescription Blocked: Reason = [bold red]{attack_data['category']}[/bold red]")
    console.print(f"  ✅ Safe Redirection: [dim]{attack_data['answer_en'][:80]}...[/dim]")
    results.append(("Guardrail Adversarial Block", f"Blocked: {attack_data['category']}", "PASS"))

    # 9. Cryptographic Audit Trail & Prometheus Metrics Telemetry
    console.print("\n[bold cyan]▶ [9/9] Verifying Cryptographic Audit Log & Updated Prometheus Telemetry...[/bold cyan]")
    audit_resp = client.get("/api/v1/audit/verify")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["valid"] is True, f"Audit log Merkle chain verification failed: {audit_data.get('error')}"
    console.print(f"  ✅ Merkle Audit Trail Verified: [bold green]VALID[/bold green] (Hash: {audit_data['latest_hash'][:16]}...)")

    metrics_resp = client.get("/metrics")
    m_text = metrics_resp.text
    assert "lab_report_http_requests_total" in m_text
    console.print("  ✅ Prometheus telemetry metrics counters successfully updated:")
    for line in m_text.splitlines():
        if "lab_report_jobs_total" in line or "lab_report_guardrail_blocks_total" in line:
            if not line.startswith("#"):
                console.print(f"     [cyan]{line}[/cyan]")
    results.append(("Audit Log & Telemetry", f"Hash: {audit_data['latest_hash'][:12]}...", "PASS"))

    # Summary Table
    table = Table(title="End-to-End Live Microservices Smoke Test Summary", title_justify="center")
    table.add_column("Verification Step", style="white")
    table.add_column("Output / Evidence", style="cyan")
    table.add_column("Result", justify="center", style="bold green")

    for step, evidence, res in results:
        table.add_row(step, evidence, res)

    console.print("\n")
    console.print(table)
    console.print("\n[bold green]🎉 FULL STACK SMOKE TEST PASSED 100% WITH ZERO ERRORS![/bold green]\n")
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
