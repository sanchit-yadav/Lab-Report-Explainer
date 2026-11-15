"""Thread-safe asynchronous JobManager for pipeline lifecycle tracking and execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from src.api.models import JobStatus
from src.explainer.pdf_export import generate_doctor_brief_pdf
from src.explainer.schema import ReportExplanation
from src.extraction.loinc_mapper import LOINCMapper
from src.extraction.schema import LabReport
from src.pipeline import LabReportPipeline

logger = logging.getLogger("job_manager")


class JobRecord:
    """Represents the mutable runtime state and artifacts of a processing job."""

    def __init__(
        self,
        job_id: str,
        filename: str,
        file_path: Path,
        file_hash: str,
        file_size_bytes: int,
    ):
        self.job_id = job_id
        self.filename = filename
        self.file_path = file_path
        self.file_hash = file_hash
        self.file_size_bytes = file_size_bytes
        self.status = JobStatus.QUEUED
        self.progress_pct = 0
        self.current_step = "Job queued for processing"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None
        self.error: Optional[str] = None
        self.explanation: Optional[ReportExplanation] = None
        self.extracted_report: Optional[Any] = None
        self.pdf_bytes: Optional[bytes] = None
        self.patient_name: Optional[str] = None
        self.total_tests: Optional[int] = None
        self.flagged_count: Optional[int] = None
        self.panic_count: Optional[int] = None

    def update_progress(self, status: JobStatus, progress_pct: int, current_step: str):
        """Update job stage and percentage."""
        self.status = status
        self.progress_pct = progress_pct
        self.current_step = current_step

    def mark_complete(
        self,
        explanation: ReportExplanation,
        pdf_bytes: bytes,
        extracted_report: Optional[Any] = None,
    ):
        """Mark job successfully completed with artifacts."""
        self.status = JobStatus.READY
        self.progress_pct = 100
        self.current_step = "Report processing complete"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.explanation = explanation
        self.pdf_bytes = pdf_bytes
        self.extracted_report = extracted_report
        self.patient_name = explanation.patient_name
        self.total_tests = explanation.total_tests
        self.flagged_count = explanation.flagged_count
        self.panic_count = len(explanation.panic_alerts)

    def mark_failed(self, error_message: str):
        """Mark job failed with diagnostic message."""
        self.status = JobStatus.FAILED
        self.progress_pct = 100
        self.current_step = "Processing failed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.error = error_message


class JobManager:
    """Singleton-ready manager tracking in-flight and historical jobs."""

    _instance: Optional["JobManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._jobs: Dict[str, JobRecord] = {}
        self._pipeline: Optional[LabReportPipeline] = None
        self._jobs_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "JobManager":
        """Get or initialize singleton JobManager instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def pipeline(self) -> LabReportPipeline:
        """Lazy load LabReportPipeline instance."""
        if self._pipeline is None:
            self._pipeline = LabReportPipeline()
        return self._pipeline

    def set_pipeline(self, pipeline: LabReportPipeline) -> None:
        """Set or mock pipeline instance for testing."""
        self._pipeline = pipeline

    def create_job(
        self,
        filename: str,
        file_path: Path,
        file_hash: str,
        file_size_bytes: int,
        job_id: Optional[str] = None,
    ) -> JobRecord:
        """Create and register a new job record."""
        job_id = job_id or str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            filename=filename,
            file_path=file_path,
            file_hash=file_hash,
            file_size_bytes=file_size_bytes,
        )
        with self._jobs_lock:
            self._jobs[job_id] = record
        logger.info(f"Registered job {job_id} for file {filename} ({file_hash[:8]}...)")
        try:
            from src.api.metrics import MetricsRegistry

            registry = MetricsRegistry.get_instance()
            registry.jobs_total.inc(status="queued")
            registry.active_jobs_gauge.inc()
        except Exception:
            pass
        return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve job record by ID."""
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> List[JobRecord]:
        """Return list of most recent jobs sorted by creation time descending."""
        with self._jobs_lock:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return sorted_jobs[:limit]

    def clear(self) -> None:
        """Clear all jobs (primarily for test isolation)."""
        with self._jobs_lock:
            self._jobs.clear()

    async def run_pipeline_job(
        self,
        job_id: str,
        explain_all: bool = False,
    ) -> None:
        """Asynchronously execute the end-to-end pipeline in a worker thread."""
        record = self.get_job(job_id)
        if not record:
            logger.error(f"Cannot run non-existent job: {job_id}")
            return

        try:
            logger.info(f"Starting execution for job {job_id}")
            record.update_progress(JobStatus.EXTRACTING, 15, "Extracting text and tables from document...")

            # Run CPU-bound extraction and model calls in threadpool
            loop = asyncio.get_running_loop()

            record.update_progress(JobStatus.FLAGGING, 35, "Evaluating clinical reference ranges & panic values...")
            record.update_progress(JobStatus.RAG_RETRIEVAL, 55, "Querying clinical guidelines via MedlinePlus RAG...")
            record.update_progress(JobStatus.GENERATING, 75, "Generating bilingual explanations & safety checks...")

            explanation: ReportExplanation = await loop.run_in_executor(
                None,
                self.pipeline.process_report,
                record.file_path,
                None,
                explain_all,
            )

            record.update_progress(JobStatus.GENERATING, 90, "Assembling Doctor Discussion Brief PDF...")
            pdf_bytes = await loop.run_in_executor(
                None,
                generate_doctor_brief_pdf,
                explanation,
                "en",
            )

            # Cache the extracted LabReport with LOINC ontology for FHIR export
            extracted_report: Optional[LabReport] = None
            try:
                extracted_report = await loop.run_in_executor(
                    None,
                    self.pipeline.extractor.extract,
                    record.file_path,
                )
                if extracted_report:
                    extracted_report = LOINCMapper.enrich_report(extracted_report)
            except Exception as e:
                logger.warning(f"Could not cache extracted_report on job: {e}")

            record.mark_complete(explanation, pdf_bytes, extracted_report=extracted_report)
            try:
                from src.api.metrics import MetricsRegistry

                registry = MetricsRegistry.get_instance()
                registry.jobs_total.inc(status="completed")
                registry.active_jobs_gauge.dec()
                if explanation and explanation.total_tests:
                    registry.extracted_tests_count.observe(explanation.total_tests)
            except Exception:
                pass
            logger.info(
                f"Job {job_id} completed successfully. "
                f"Patient: {explanation.patient_name}, Tests: {explanation.total_tests}"
            )

        except Exception as e:
            logger.exception(f"Job {job_id} failed with error: {e}")
            try:
                from src.api.metrics import MetricsRegistry
                from src.monitoring.sentry import capture_exception

                capture_exception(e, tags={"job_id": job_id})
                registry = MetricsRegistry.get_instance()
                registry.jobs_total.inc(status="failed")
                registry.active_jobs_gauge.dec()
            except Exception:
                pass
            record.mark_failed(str(e))
