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
        user_id: Optional[str] = None,
    ):
        self.job_id = job_id
        self.user_id = user_id
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
        self._persist_to_db()

    def mark_failed(self, error_message: str):
        """Mark job failed with diagnostic message."""
        self.status = JobStatus.FAILED
        self.progress_pct = 100
        self.current_step = "Processing failed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.error = error_message
        self._persist_to_db()

    def _persist_to_db(self) -> None:
        """Persist or update state in relational database."""
        try:
            from src.db.session import SessionLocal
            from src.db.models import Report, TestRecord

            with SessionLocal() as db:
                db_report = db.query(Report).filter(Report.id == self.job_id).first()
                if not db_report:
                    db_report = Report(
                        id=self.job_id,
                        user_id=self.user_id,
                        filename=self.filename,
                        file_hash=self.file_hash,
                        file_size_bytes=self.file_size_bytes,
                        status=self.status.value if hasattr(self.status, "value") else str(self.status),
                        progress_pct=self.progress_pct,
                        patient_name=self.patient_name,
                        error=self.error,
                    )
                    db.add(db_report)
                else:
                    db_report.status = self.status.value if hasattr(self.status, "value") else str(self.status)
                    db_report.progress_pct = self.progress_pct
                    db_report.patient_name = self.patient_name
                    db_report.error = self.error

                if self.file_path:
                    db_report.pdf_path = str(self.file_path)
                if self.explanation:
                    db_report.explanation_data = self.explanation.model_dump_json()
                if self.extracted_report:
                    db_report.extracted_data = self.extracted_report.model_dump_json()

                if self.extracted_report and getattr(self.extracted_report, "tests", None):
                    db.query(TestRecord).filter(TestRecord.report_id == self.job_id).delete()
                    for t in self.extracted_report.tests:
                        tr = TestRecord(
                            report_id=self.job_id,
                            user_id=self.user_id,
                            test_name=t.test_name,
                            value=t.value,
                            raw_value=t.raw_value,
                            unit=t.unit,
                            ref_low=t.ref_low,
                            ref_high=t.ref_high,
                            ref_raw=t.ref_raw,
                            flag=t.flag.value if hasattr(t.flag, "value") else str(t.flag),
                            loinc_code=t.loinc_code,
                            loinc_name=t.loinc_name,
                            category=t.category,
                        )
                        db.add(tr)
                db.commit()
        except Exception as exc:
            logger.warning(f"Failed to persist report {self.job_id} to database: {exc}")


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
        user_id: Optional[str] = None,
    ) -> JobRecord:
        """Create and register a new job record."""
        job_id = job_id or str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            filename=filename,
            file_path=file_path,
            file_hash=file_hash,
            file_size_bytes=file_size_bytes,
            user_id=user_id,
        )
        with self._jobs_lock:
            self._jobs[job_id] = record
        record._persist_to_db()
        logger.info(f"Registered job {job_id} for file {filename} ({file_hash[:8]}...)")
        try:
            from src.api.metrics import MetricsRegistry

            registry = MetricsRegistry.get_instance()
            registry.jobs_total.inc(status="queued")
            registry.active_jobs_gauge.inc()
        except Exception:
            pass
        return record

    def _job_record_from_db(self, db_report: Any) -> JobRecord:
        """Hydrate an in-memory JobRecord from a persistent database Report model."""
        rec = JobRecord(
            job_id=db_report.id,
            filename=db_report.filename or "report.pdf",
            file_path=Path(db_report.pdf_path) if db_report.pdf_path else Path(""),
            file_hash=db_report.file_hash or "",
            file_size_bytes=db_report.file_size_bytes or 0,
            user_id=db_report.user_id,
        )
        try:
            rec.status = JobStatus(db_report.status)
        except Exception:
            rec.status = JobStatus.READY if str(db_report.status).lower() == "ready" else JobStatus.QUEUED

        rec.progress_pct = db_report.progress_pct or (100 if rec.status == JobStatus.READY else 0)
        rec.patient_name = db_report.patient_name
        rec.error = db_report.error
        rec.created_at = db_report.created_at.isoformat() if db_report.created_at else datetime.now(timezone.utc).isoformat()
        rec.completed_at = db_report.updated_at.isoformat() if db_report.updated_at else None

        if db_report.extracted_data:
            try:
                rec.extracted_report = LabReport.model_validate_json(db_report.extracted_data)
            except Exception as e:
                logger.warning(f"Failed to deserialize extracted_data for job {db_report.id}: {e}")

        if db_report.explanation_data:
            try:
                rec.explanation = ReportExplanation.model_validate_json(db_report.explanation_data)
                rec.total_tests = rec.explanation.total_tests
                rec.flagged_count = rec.explanation.flagged_count
                rec.panic_count = len(rec.explanation.panic_alerts)
            except Exception as e:
                logger.warning(f"Failed to deserialize explanation_data for job {db_report.id}: {e}")

        if db_report.pdf_path and Path(db_report.pdf_path).exists():
            try:
                rec.pdf_bytes = Path(db_report.pdf_path).read_bytes()
            except Exception:
                pass

        return rec

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve job record by ID from memory, or fallback to relational DB."""
        with self._jobs_lock:
            rec = self._jobs.get(job_id)
            if rec:
                return rec

        try:
            from src.db.session import SessionLocal
            from src.db.models import Report

            with SessionLocal() as db:
                db_report = db.query(Report).filter(Report.id == job_id).first()
                if db_report:
                    rec = self._job_record_from_db(db_report)
                    with self._jobs_lock:
                        self._jobs[job_id] = rec
                    return rec
        except Exception as exc:
            logger.warning(f"Error querying job {job_id} from database: {exc}")

        return None

    def list_jobs(self, limit: int = 50, user_id: Optional[str] = None) -> List[JobRecord]:
        """Return list of most recent jobs sorted by creation time descending, querying DB for persistence."""
        db_records_map: Dict[str, JobRecord] = {}

        # 1. Query database for persistent historical records
        try:
            from src.db.session import SessionLocal
            from src.db.models import Report

            with SessionLocal() as db:
                query = db.query(Report)
                if user_id:
                    query = query.filter(Report.user_id == user_id)
                db_reports = query.order_by(Report.created_at.desc()).limit(limit).all()
                for r in db_reports:
                    db_records_map[r.id] = self._job_record_from_db(r)
        except Exception as exc:
            logger.warning(f"Database query error in list_jobs: {exc}")

        # 2. Merge with any currently in-flight in-memory jobs (in-memory has real-time progress)
        with self._jobs_lock:
            for jid, jrec in self._jobs.items():
                if user_id and jrec.user_id and jrec.user_id != user_id:
                    continue
                db_records_map[jid] = jrec

        sorted_jobs = sorted(
            db_records_map.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )
        return sorted_jobs[:limit]

    def delete_job(self, job_id: str, user_id: Optional[str] = None) -> bool:
        """Permanently delete a job, associated DB records, in-memory cache, and disk files."""
        deleted = False
        file_to_delete: Optional[Path] = None

        # 1. Remove from in-memory cache
        with self._jobs_lock:
            if job_id in self._jobs:
                rec = self._jobs[job_id]
                if user_id and rec.user_id and rec.user_id != user_id:
                    return False
                if rec.file_path and Path(rec.file_path).exists():
                    file_to_delete = Path(rec.file_path)
                del self._jobs[job_id]
                deleted = True

        # 2. Remove from relational database (cascade removes test_records)
        try:
            from src.db.session import SessionLocal
            from src.db.models import Report

            with SessionLocal() as db:
                query = db.query(Report).filter(Report.id == job_id)
                if user_id:
                    query = query.filter(Report.user_id == user_id)
                db_report = query.first()
                if db_report:
                    if db_report.pdf_path and Path(db_report.pdf_path).exists():
                        file_to_delete = Path(db_report.pdf_path)
                    db.delete(db_report)
                    db.commit()
                    deleted = True
        except Exception as exc:
            logger.error(f"Error deleting job {job_id} from database: {exc}")
            raise

        # 3. Clean up physical file on disk
        if file_to_delete and file_to_delete.exists():
            try:
                file_to_delete.unlink(missing_ok=True)
                logger.info(f"Deleted upload artifact {file_to_delete}")
            except Exception as e:
                logger.warning(f"Could not delete physical file {file_to_delete}: {e}")

        return deleted

    def clear(self) -> None:
        """Clear all in-memory jobs (primarily for test isolation)."""
        with self._jobs_lock:
            self._jobs.clear()

    async def run_pipeline_job(
        self,
        job_id: str,
        explain_all: bool = False,
        auto_confirm: bool = True,
    ) -> None:
        """Asynchronously execute report processing (either end-to-end or stopping for review)."""
        record = self.get_job(job_id)
        if not record:
            logger.error(f"Cannot run non-existent job: {job_id}")
            return

        try:
            logger.info(f"Starting execution for job {job_id} (auto_confirm={auto_confirm})")
            record.update_progress(JobStatus.EXTRACTING, 15, "Extracting text and tables from document...")
            loop = asyncio.get_running_loop()

            if not auto_confirm:
                # Stage 1: Extraction & initial deterministic flagging only
                extracted_report: Optional[LabReport] = await loop.run_in_executor(
                    None,
                    self.pipeline.extractor.extract,
                    record.file_path,
                )
                if extracted_report:
                    extracted_report = LOINCMapper.enrich_report(extracted_report)
                    extracted_report = self.pipeline.flagger.flag_report(extracted_report)
                    record.extracted_report = extracted_report
                    record.patient_name = extracted_report.patient_name
                    record.total_tests = len(extracted_report.tests)
                    record.flagged_count = sum(
                        1 for t in extracted_report.tests if t.flag.value not in ("normal", "unknown")
                    )

                record.update_progress(
                    JobStatus.REVIEW_NEEDED,
                    40,
                    "Extraction complete. Review parameters before generating explanations.",
                )
                record._persist_to_db()
                logger.info(f"Job {job_id} awaiting user review with {record.total_tests} parameters.")
                return

            # Auto-confirm mode: Full end-to-end execution
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

    async def confirm_and_explain_job(
        self,
        job_id: str,
        confirmed_report: LabReport,
        explain_all: bool = False,
    ) -> None:
        """Resume job processing after human review of extracted parameters."""
        record = self.get_job(job_id)
        if not record:
            logger.error(f"Cannot confirm non-existent job: {job_id}")
            return

        try:
            record.extracted_report = confirmed_report
            record.patient_name = confirmed_report.patient_name
            record.total_tests = len(confirmed_report.tests)

            loop = asyncio.get_running_loop()
            record.update_progress(JobStatus.FLAGGING, 50, "Evaluating clinical reference ranges & panic values...")
            record.update_progress(JobStatus.RAG_RETRIEVAL, 65, "Querying clinical guidelines via MedlinePlus RAG...")
            record.update_progress(JobStatus.GENERATING, 80, "Generating bilingual explanations & safety checks...")

            explanation = await loop.run_in_executor(
                None,
                self.pipeline.explain_lab_report,
                confirmed_report,
                explain_all,
            )

            record.update_progress(JobStatus.GENERATING, 92, "Assembling Doctor Discussion Brief PDF...")
            pdf_bytes = await loop.run_in_executor(
                None,
                generate_doctor_brief_pdf,
                explanation,
                "en",
            )

            record.mark_complete(explanation, pdf_bytes, extracted_report=confirmed_report)
            try:
                from src.api.metrics import MetricsRegistry

                registry = MetricsRegistry.get_instance()
                registry.jobs_total.inc(status="completed")
                registry.active_jobs_gauge.dec()
                if explanation and explanation.total_tests:
                    registry.extracted_tests_count.observe(explanation.total_tests)
            except Exception:
                pass
            logger.info(f"Job {job_id} confirmed and completed successfully.")
        except Exception as e:
            logger.exception(f"Job {job_id} confirmation/explanation failed: {e}")
            record.mark_failed(str(e))
