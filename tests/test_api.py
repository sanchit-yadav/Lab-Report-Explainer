"""Unit and integration tests for FastAPI REST API endpoints."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.api.main import app
from src.api.models import JobStatus
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.workers.job_manager import JobManager


@pytest.fixture(autouse=True)
def clean_job_manager():
    """Ensure a clean job manager registry before and after every test."""
    jm = JobManager.get_instance()
    jm.clear()
    yield
    jm.clear()


@pytest.fixture
def client():
    """TestClient fixture for FastAPI app."""
    return TestClient(app)


def test_healthz_endpoint(client):
    """Liveness probe /healthz should return 200 OK and timestamp."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_readyz_endpoint_healthy(client):
    """Readiness probe /readyz returns 200 when all diagnostics pass."""
    with patch("src.api.main.run_health_check") as mock_check:
        mock_check.return_value = {
            "status": "healthy",
            "config_valid": True,
            "models": {"gemini_configured": True},
            "rag": {"ready": True},
        }
        response = client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["status"] == "ready"


def test_readyz_endpoint_degraded(client):
    """Readiness probe /readyz returns 503 when services are degraded."""
    with patch("src.api.main.run_health_check") as mock_check:
        mock_check.return_value = {
            "status": "degraded",
            "config_valid": True,
            "models": {"gemini_configured": False},
        }
        response = client.get("/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["status"] == "degraded"


def test_upload_invalid_extension(client):
    """Upload rejects unsupported file types with 415 Unsupported Media Type."""
    files = {"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")}
    response = client.post("/api/v1/reports/upload", files=files)
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_empty_file(client):
    """Upload rejects empty files with 400 Bad Request."""
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    response = client.post("/api/v1/reports/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_upload_valid_pdf_enqueues_job(client, tmp_path):
    """Upload accepts valid PDF, creates job, and returns 202 Accepted."""
    content = b"%PDF-1.4 mock pdf content for testing"
    files = {"file": ("cbc_report.pdf", content, "application/pdf")}

    with patch("src.workers.job_manager.JobManager.run_pipeline_job"):
        response = client.post("/api/v1/reports/upload", files=files)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["filename"] == "cbc_report.pdf"
        assert data["status"] == "queued"
        assert len(data["file_hash"]) == 64


def test_get_job_status_not_found(client):
    """Polling status for non-existent job returns 404."""
    response = client.get("/api/v1/reports/00000000-0000-0000-0000-000000000000/status")
    assert response.status_code == 404


def test_get_job_status_success(client, tmp_path):
    """Polling status for an active job returns proper metadata."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")

    record = jm.create_job(
        filename="report.pdf",
        file_path=dummy_file,
        file_hash="dummyhash123",
        file_size_bytes=8,
    )
    record.update_progress(JobStatus.FLAGGING, 45, "Flagging analytes")

    response = client.get(f"/api/v1/reports/{record.job_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == record.job_id
    assert data["status"] == "flagging"
    assert data["progress_pct"] == 45
    assert data["current_step"] == "Flagging analytes"


def test_get_explanation_conflict_when_pending(client, tmp_path):
    """Fetching explanation while job is still processing returns 409 Conflict."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash", 8)

    response = client.get(f"/api/v1/reports/{record.job_id}/explanation")
    assert response.status_code == 409


def test_get_explanation_success(client, tmp_path):
    """Fetching explanation when job is READY returns complete JSON payload."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash", 8)

    mock_exp = ReportExplanation(
        patient_name="Rahul Sharma",
        report_summary_en="All biomarkers stable.",
        report_summary_hi="सभी बायोमार्कर स्थिर हैं।",
        total_tests=1,
        flagged_count=0,
        test_explanations=[
            TestExplanation(
                test_name="Hemoglobin",
                value=14.5,
                unit="g/dL",
                flag=FlagStatus.NORMAL,
                explanation_en="Normal oxygen-carrying protein.",
                explanation_hi="सामान्य ऑक्सीजन-वाहक प्रोटीन।",
            )
        ],
    )
    record.mark_complete(mock_exp, b"%PDF-DoctorBrief")

    response = client.get(f"/api/v1/reports/{record.job_id}/explanation")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_name"] == "Rahul Sharma"
    assert len(data["test_explanations"]) == 1
    assert data["test_explanations"][0]["test_name"] == "Hemoglobin"


def test_download_doctor_brief_pdf(client, tmp_path):
    """Streaming PDF returns 200 with application/pdf headers."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash", 8)

    mock_exp = ReportExplanation(report_summary_en="Summary", report_summary_hi="सारांश")
    record.mark_complete(mock_exp, b"%PDF-1.4 Mock PDF Stream Data")

    response = client.get(f"/api/v1/reports/{record.job_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert response.content == b"%PDF-1.4 Mock PDF Stream Data"


def test_qa_endpoint(client, tmp_path):
    """Posting question returns guardrailed answer and citations."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash", 8)

    mock_exp = ReportExplanation(patient_name="John Doe", report_summary_en="Summary", report_summary_hi="सारांश")
    record.mark_complete(mock_exp, b"%PDF")

    mock_pipeline = MagicMock()
    mock_pipeline.answer_question.return_value = {
        "blocked": False,
        "category": None,
        "answer_en": "Hemoglobin transports oxygen throughout the body.",
        "answer_hi": "हीमोग्लोबिन शरीर में ऑक्सीजन पहुंचाता है।",
        "source_urls": ["https://medlineplus.gov/lab-tests/hemoglobin/"],
        "disclaimer": "Educational only.",
        "elapsed_ms": 120.0,
    }
    jm.set_pipeline(mock_pipeline)

    payload = {
        "question": "What is the function of hemoglobin?",
        "chat_history": [{"role": "user", "content": "Hello"}],
    }
    response = client.post(f"/api/v1/reports/{record.job_id}/qa", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["blocked"] is False
    assert "transports oxygen" in data["answer_en"]
    assert len(data["source_urls"]) == 1


def test_list_recent_jobs_endpoint(client, tmp_path):
    """Listing recent jobs returns array of job status summaries."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")

    jm.create_job("report1.pdf", dummy_file, "hash1", 10)
    jm.create_job("report2.pdf", dummy_file, "hash2", 20)

    response = client.get("/api/v1/reports?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_upload_rejects_embedded_exploit(client):
    """Uploading a PDF with embedded JavaScript or Launch actions returns 400 Bad Request."""
    malicious_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Action /S /JavaScript /JS (alert('hack')) >>\nendobj"
    files = {"file": ("report_exploit.pdf", malicious_pdf, "application/pdf")}
    response = client.post("/api/v1/reports/upload", files=files)
    assert response.status_code == 400
    assert "Security check failed" in response.json()["detail"]


def test_audit_verify_and_logs_endpoints(client):
    """Audit verification and log inspection endpoints return valid Merkle status."""
    verify_resp = client.get("/api/v1/audit/verify")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert "valid" in verify_data
    assert "latest_hash" in verify_data

    logs_resp = client.get("/api/v1/audit/logs?limit=20")
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert isinstance(logs_data, list)


def test_get_fhir_bundle_endpoint(client, tmp_path):
    """Retrieving FHIR bundle for a completed job returns a valid FHIR R4 Bundle."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash999", 8)

    mock_raw_report = LabReport(
        patient_name="Ananya Sen",
        tests=[TestResult(test_name="Hemoglobin", value=14.0, unit="g/dL", flag=FlagStatus.NORMAL)],
    )
    mock_exp = ReportExplanation(
        patient_name="Ananya Sen",
        report_summary_en="Healthy report.",
        report_summary_hi="स्वस्थ रिपोर्ट।",
        total_tests=1,
        flagged_count=0,
        test_explanations=[
            TestExplanation(
                test_name="Hemoglobin",
                flag=FlagStatus.NORMAL,
                explanation_en="Normal oxygen-carrying protein.",
                explanation_hi="सामान्य प्रोटीन।",
            )
        ],
    )
    record.mark_complete(mock_exp, b"%PDF-DoctorBrief", extracted_report=mock_raw_report)

    response = client.get(f"/api/v1/reports/{record.job_id}/fhir")
    assert response.status_code == 200
    bundle = response.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["total"] >= 2  # 1 DiagnosticReport + 1 Observation
