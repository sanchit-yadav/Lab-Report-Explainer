"""Unit and integration tests for FastAPI REST API endpoints."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

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

    j1 = jm.create_job("report1.pdf", dummy_file, "hash1", 10)
    j2 = jm.create_job("report2.pdf", dummy_file, "hash2", 20)

    response = client.get("/api/v1/reports?limit=10")
    assert response.status_code == 200
    data = response.json()
    job_ids = [j["job_id"] for j in data]
    assert j1.job_id in job_ids
    assert j2.job_id in job_ids


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


def test_get_extracted_report_not_ready(client, tmp_path):
    """GET /extracted returns 409 Conflict if extraction has not completed yet."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash409", 8)

    response = client.get(f"/api/v1/reports/{record.job_id}/extracted")
    assert response.status_code == 409


def test_get_extracted_report_success(client, tmp_path):
    """GET /extracted returns structured biomarker parameters for human review."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hash200", 8)
    record.status = JobStatus.REVIEW_NEEDED
    record.extracted_report = LabReport(
        patient_name="Pooja Verma",
        tests=[
            TestResult(
                test_name="Fasting Blood Glucose",
                value=126.0,
                unit="mg/dL",
                ref_low=70.0,
                ref_high=99.0,
                flag=FlagStatus.HIGH,
            )
        ],
    )
    record.patient_name = "Pooja Verma"

    response = client.get(f"/api/v1/reports/{record.job_id}/extracted")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_name"] == "Pooja Verma"
    assert data["total_tests"] == 1
    assert data["tests"][0]["test_name"] == "Fasting Blood Glucose"
    assert data["tests"][0]["value"] == 126.0
    assert data["tests"][0]["flag"] == "high"


def test_confirm_report_triggers_explanation(client, tmp_path):
    """POST /confirm updates parameters with user corrections and enqueues explanation."""
    jm = JobManager.get_instance()
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("report.pdf", dummy_file, "hashconfirm", 8)
    record.status = JobStatus.REVIEW_NEEDED

    payload = {
        "patient_name": "Pooja V. (Corrected)",
        "tests": [
            {
                "test_name": "Fasting Blood Glucose",
                "value": 95.0,  # User corrected value to normal
                "unit": "mg/dL",
                "ref_low": 70.0,
                "ref_high": 99.0,
            }
        ],
        "explain_all": False,
    }

    with patch("src.workers.job_manager.JobManager.confirm_and_explain_job") as mock_confirm:
        response = client.post(f"/api/v1/reports/{record.job_id}/confirm", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == record.job_id
        assert data["confirmed_tests_count"] == 1
        assert "Parameters confirmed" in data["message"]


def test_delete_report_workflow(client, tmp_path):
    """DELETE /api/v1/reports/{job_id} removes report from memory, database, and disk."""
    from src.api.auth import create_access_token
    from src.db.session import SessionLocal
    from src.db.models import User, Report

    # Create test user
    uid = str(uuid.uuid4())
    with SessionLocal() as db:
        user = User(id=uid, email=f"del_{uid[:6]}@example.com", hashed_password="pw")
        db.add(user)
        db.commit()

    token = create_access_token(subject=uid)
    headers = {"Authorization": f"Bearer {token}"}

    jm = JobManager.get_instance()
    dummy_file = tmp_path / "del_report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("del_report.pdf", dummy_file, f"hashdel_{uid[:4]}", 8, user_id=uid)
    record.status = JobStatus.READY
    record._persist_to_db()

    # Verify report exists in DB
    with SessionLocal() as db:
        assert db.query(Report).filter(Report.id == record.job_id).first() is not None

    # Delete report
    del_resp = client.delete(f"/api/v1/reports/{record.job_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify removed from in-memory cache and DB
    assert jm.get_job(record.job_id) is None
    with SessionLocal() as db:
        assert db.query(Report).filter(Report.id == record.job_id).first() is None


def test_delete_report_unauthorized(client, tmp_path):
    """A user cannot delete another patient's laboratory report (403 Forbidden)."""
    from src.api.auth import create_access_token
    from src.db.session import SessionLocal
    from src.db.models import User

    uid1 = str(uuid.uuid4())
    uid2 = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(User(id=uid1, email=f"u1_{uid1[:6]}@example.com", hashed_password="pw"))
        db.add(User(id=uid2, email=f"u2_{uid2[:6]}@example.com", hashed_password="pw"))
        db.commit()

    token_user2 = create_access_token(subject=uid2)
    headers_user2 = {"Authorization": f"Bearer {token_user2}"}

    jm = JobManager.get_instance()
    dummy_file = tmp_path / "u1_report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("u1_report.pdf", dummy_file, f"hashu1_{uid1[:4]}", 8, user_id=uid1)
    record._persist_to_db()

    # User 2 attempts to delete User 1's report
    del_resp = client.delete(f"/api/v1/reports/{record.job_id}", headers=headers_user2)
    assert del_resp.status_code == 403


def test_history_persistence_across_memory_clear(client, tmp_path):
    """GET /api/v1/reports and get_job retrieve historical reports from SQLite even after in-memory cache is cleared."""
    from src.api.auth import create_access_token
    from src.db.session import SessionLocal
    from src.db.models import User

    uid = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"persist_{uid[:6]}@example.com", hashed_password="pw"))
        db.commit()

    token = create_access_token(subject=uid)
    headers = {"Authorization": f"Bearer {token}"}

    jm = JobManager.get_instance()
    dummy_file = tmp_path / "persist_test.pdf"
    dummy_file.write_bytes(b"%PDF-1.4")
    record = jm.create_job("persist_test.pdf", dummy_file, f"hashpersist_{uid[:4]}", 8, user_id=uid)
    record.status = JobStatus.READY
    record.patient_name = "Persistent Patient"
    record._persist_to_db()

    # Simulate server reboot / in-memory cache wipe
    jm.clear()
    assert record.job_id not in jm._jobs

    # Verify JobManager rehydrates from SQLite
    rehydrated = jm.get_job(record.job_id)
    assert rehydrated is not None
    assert rehydrated.patient_name == "Persistent Patient"
    assert rehydrated.status == JobStatus.READY

    # Verify REST API /api/v1/reports returns historical reports
    resp = client.get("/api/v1/reports", headers=headers)
    assert resp.status_code == 200
    jobs = resp.json()
    job_ids = [j["job_id"] for j in jobs]
    assert record.job_id in job_ids


def test_root_serves_react_spa(client):
    """Root endpoint / serves the compiled React 19 SPA index.html."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert '<div id="root">' in resp.text

