"""Celery distributed task worker integration for horizontal scaling."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from src.explainer.pdf_export import generate_doctor_brief_pdf
from src.explainer.schema import ReportExplanation
from src.pipeline import LabReportPipeline
from src.workers.job_manager import JobManager, JobStatus

logger = logging.getLogger("celery_tasks")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_AVAILABLE = False

try:
    from celery import Celery

    celery_app = Celery(
        "lab_report_explainer",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,  # Fair distribution for heavy OCR tasks
        task_acks_late=True,  # Ensure task re-queues if worker pod dies
    )
    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None
    logger.info("Celery is not installed. Defaulting to native asyncio JobManager.")


def run_pipeline_sync(
    job_id: str,
    file_path_str: str,
    explain_all: bool = False,
) -> Dict[str, Any]:
    """Synchronous pipeline task suitable for distributed Celery execution."""
    job_mgr = JobManager.get_instance()
    record = job_mgr.get_job(job_id)
    if not record:
        record = job_mgr.create_job(
            filename=Path(file_path_str).name,
            file_path=Path(file_path_str),
            file_hash="",
            file_size_bytes=os.path.getsize(file_path_str) if os.path.exists(file_path_str) else 0,
            job_id=job_id,
        )

    try:
        record.update_progress(JobStatus.EXTRACTING, 20, "Extracting document data in worker...")
        pipeline = LabReportPipeline()

        record.update_progress(
            JobStatus.FLAGGING, 40, "Flagging reference ranges & panic values..."
        )
        explanation: ReportExplanation = pipeline.process_report(
            Path(file_path_str),
            None,
            explain_all,
        )

        record.update_progress(JobStatus.GENERATING, 80, "Rendering Doctor Brief PDF...")
        pdf_bytes = generate_doctor_brief_pdf(explanation, "en")

        record.mark_complete(explanation, pdf_bytes)
        return {
            "job_id": job_id,
            "status": "ready",
            "patient_name": explanation.patient_name,
            "total_tests": explanation.total_tests,
            "flagged_count": explanation.flagged_count,
        }
    except Exception as e:
        record.mark_failed(str(e))
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
        }


if CELERY_AVAILABLE and celery_app is not None:

    @celery_app.task(name="tasks.process_lab_report", bind=True)
    def process_lab_report_task(self, job_id: str, file_path_str: str, explain_all: bool = False):
        """Celery task entrypoint."""
        return run_pipeline_sync(job_id, file_path_str, explain_all)
