"""Unit tests for background task worker and JobManager."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.api.models import JobStatus
from src.explainer.schema import ReportExplanation
from src.workers.job_manager import JobManager, JobRecord
from src.workers.tasks import run_pipeline_sync


@pytest.fixture(autouse=True)
def clean_job_manager():
    """Ensure clean manager state for each test."""
    jm = JobManager.get_instance()
    jm.clear()
    yield
    jm.clear()


def test_job_record_lifecycle(tmp_path):
    """Verify JobRecord state transitions from QUEUED to READY or FAILED."""
    fake_file = tmp_path / "test.pdf"
    fake_file.write_bytes(b"content")

    record = JobRecord("test-job-1", "test.pdf", fake_file, "hash123", 7)
    assert record.status == JobStatus.QUEUED
    assert record.progress_pct == 0

    record.update_progress(JobStatus.EXTRACTING, 25, "Extracting text")
    assert record.status == JobStatus.EXTRACTING
    assert record.progress_pct == 25
    assert record.current_step == "Extracting text"

    mock_exp = ReportExplanation(
        patient_name="Anita Roy",
        report_summary_en="Normal",
        report_summary_hi="सामान्य",
        total_tests=5,
        flagged_count=1,
    )
    record.mark_complete(mock_exp, b"%PDF-DATA")
    assert record.status == JobStatus.READY
    assert record.progress_pct == 100
    assert record.patient_name == "Anita Roy"
    assert record.total_tests == 5
    assert record.flagged_count == 1
    assert record.pdf_bytes == b"%PDF-DATA"
    assert record.completed_at is not None

    record_fail = JobRecord("test-job-2", "test.pdf", fake_file, "hash456", 7)
    record_fail.mark_failed("Corrupt PDF syntax")
    assert record_fail.status == JobStatus.FAILED
    assert record_fail.error == "Corrupt PDF syntax"
    assert record_fail.completed_at is not None


def test_job_manager_async_execution_success(tmp_path):
    """JobManager executes asynchronous pipeline and marks job ready."""
    jm = JobManager.get_instance()
    dummy_pdf = tmp_path / "blood_test.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 mock")

    record = jm.create_job("blood_test.pdf", dummy_pdf, "abc123hash", 14)

    mock_pipeline = MagicMock()
    mock_exp = ReportExplanation(
        patient_name="Sameer Verma",
        report_summary_en="Optimal levels.",
        report_summary_hi="उत्तम स्तर।",
        total_tests=3,
        flagged_count=0,
    )
    mock_pipeline.process_report.return_value = mock_exp
    jm.set_pipeline(mock_pipeline)

    with patch("src.workers.job_manager.generate_doctor_brief_pdf", return_value=b"%PDF-Doctor-Brief"):
        asyncio.run(jm.run_pipeline_job(record.job_id))

    updated = jm.get_job(record.job_id)
    assert updated is not None
    assert updated.status == JobStatus.READY
    assert updated.progress_pct == 100
    assert updated.patient_name == "Sameer Verma"
    assert updated.pdf_bytes == b"%PDF-Doctor-Brief"


def test_job_manager_async_execution_failure(tmp_path):
    """JobManager records failure when pipeline raises an exception."""
    jm = JobManager.get_instance()
    dummy_pdf = tmp_path / "broken.pdf"
    dummy_pdf.write_bytes(b"bad content")

    record = jm.create_job("broken.pdf", dummy_pdf, "badhash", 11)

    mock_pipeline = MagicMock()
    mock_pipeline.process_report.side_effect = RuntimeError("OCR engine timeout")
    jm.set_pipeline(mock_pipeline)

    asyncio.run(jm.run_pipeline_job(record.job_id))

    updated = jm.get_job(record.job_id)
    assert updated is not None
    assert updated.status == JobStatus.FAILED
    assert "OCR engine timeout" in str(updated.error)


def test_run_pipeline_sync_worker_task(tmp_path):
    """Synchronous worker task function successfully finishes and returns summary dict."""
    dummy_pdf = tmp_path / "cbc.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4")

    mock_exp = ReportExplanation(
        patient_name="Pooja Patel",
        report_summary_en="Good health.",
        report_summary_hi="अच्छा स्वास्थ्य।",
        total_tests=8,
        flagged_count=1,
    )

    with patch("src.workers.tasks.LabReportPipeline") as MockPipelineCls, \
         patch("src.workers.tasks.generate_doctor_brief_pdf", return_value=b"%PDF-BRIEF"):
        mock_instance = MagicMock()
        mock_instance.process_report.return_value = mock_exp
        MockPipelineCls.return_value = mock_instance

        res = run_pipeline_sync("task-uuid-1", str(dummy_pdf))

        assert res["job_id"] == "task-uuid-1"
        assert res["status"] == "ready"
        assert res["patient_name"] == "Pooja Patel"
        assert res["total_tests"] == 8
