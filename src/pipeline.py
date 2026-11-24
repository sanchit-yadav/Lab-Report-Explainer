"""Pipeline orchestrator unifying extraction, deterministic flagging, RAG, and guardrails."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Union

from src.config import get_config
from src.explainer.generator import ExplanationGenerator
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.loinc_mapper import LOINCMapper
from src.extraction.router import ExtractionRouter
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.flagging.correlations import CorrelationEngine
from src.flagging.demographics import DemographicIntervalEngine
from src.flagging.flagger import Flagger
from src.flagging.interferences import DrugInterferenceEngine
from src.flagging.lifestyle import LifestyleEngine
from src.flagging.panic_values import PanicValueEngine
from src.guardrails.input_guard import GuardrailResult, InputGuard
from src.guardrails.output_guard import OutputGuard
from src.history.tracker import HistoryTracker
from src.privacy.deidentifier import PHIDeidentifier
from src.rag.reranker import CrossEncoderReranker
from src.rag.retriever import ChromaRetriever
from src.security.audit import SecurityAuditLogger
from src.stages import (
    ExplainInput,
    ExplainOutput,
    ExplainStage,
    ExtractionOutputItem,
    ExtractValuesInput,
    ExtractValuesOutput,
    ExtractValuesStage,
    OCRParseInput,
    OCRParseOutput,
    OCRParseStage,
    OutputGuardInput,
    OutputGuardOutput,
    OutputGuardStage,
    RetrieveInput,
    RetrieveOutput,
    RetrieveStage,
    ValidateUploadInput,
    ValidateUploadOutput,
    ValidateUploadStage,
    generate_request_id,
)
from src.tracing.langfuse_setup import get_tracer

logger = logging.getLogger("pipeline")


class LabReportPipeline:
    """End-to-end orchestration pipeline for the AI Lab Report Explainer."""

    def __init__(self):
        self.config = get_config()
        self.tracer = get_tracer()
        self.extractor = ExtractionRouter()
        self.flagger = Flagger(self.config.extraction.flagging)
        self.retriever = ChromaRetriever(self.config.rag)
        self.reranker = CrossEncoderReranker(self.config.rag.reranker)
        self.generator = ExplanationGenerator()
        self.input_guard = InputGuard()
        self.output_guard = OutputGuard()
        self.correlation_engine = CorrelationEngine()
        self.history_tracker = HistoryTracker()
        self.panic_engine = PanicValueEngine()
        self.interference_engine = DrugInterferenceEngine()
        self.lifestyle_engine = LifestyleEngine()
        self.deidentifier = PHIDeidentifier()
        self.audit_logger = SecurityAuditLogger.get_instance()

        # Decoupled pipeline stage instances (Phase 1 Refactor)
        self.stage_validate = ValidateUploadStage()
        self.stage_ocr = OCRParseStage()
        self.stage_extract = ExtractValuesStage()
        self.stage_retrieve = RetrieveStage()
        self.stage_explain = ExplainStage()
        self.stage_output_guard = OutputGuardStage()

    def run_stage_validate(
        self, file_bytes: bytes, filename: str, request_id: Optional[str] = None
    ) -> ValidateUploadOutput:
        """Execute Stage 1: Upload Validation & Security Sanitization."""
        req_id = request_id or generate_request_id()
        return self.stage_validate(
            ValidateUploadInput(file_bytes=file_bytes, filename=filename, request_id=req_id)
        )

    def run_stage_ocr(
        self, file_bytes: bytes, filename: str, request_id: Optional[str] = None
    ) -> OCRParseOutput:
        """Execute Stage 2: OCR & Layout Geometry Parsing."""
        req_id = request_id or generate_request_id()
        return self.stage_ocr(
            OCRParseInput(file_bytes=file_bytes, filename=filename, request_id=req_id)
        )

    def run_stage_extract(
        self,
        parsed_doc: OCRParseOutput,
        raw_bytes: Optional[bytes] = None,
        request_id: Optional[str] = None,
    ) -> ExtractValuesOutput:
        """Execute Stage 3: Biomarker Value Extraction with Deterministic Range Flagging."""
        req_id = request_id or generate_request_id()
        return self.stage_extract(
            ExtractValuesInput(parsed_doc=parsed_doc, raw_bytes=raw_bytes, request_id=req_id)
        )

    def run_stage_retrieve(
        self, queries: List[str], request_id: Optional[str] = None
    ) -> RetrieveOutput:
        """Execute Stage 4: Clinical Knowledge Retrieval & Cross-Encoder Reranking."""
        req_id = request_id or generate_request_id()
        return self.stage_retrieve(RetrieveInput(queries=queries, request_id=req_id))

    def run_stage_explain(
        self,
        extraction: ExtractValuesOutput,
        retrieved: RetrieveOutput,
        request_id: Optional[str] = None,
        explain_all: bool = False,
    ) -> ExplainOutput:
        """Execute Stage 5: Bilingual Clinical Explanation Synthesis."""
        req_id = request_id or generate_request_id()
        return self.stage_explain(
            ExplainInput(
                request_id=req_id,
                extraction=extraction,
                retrieved_knowledge=retrieved,
                explain_all=explain_all,
            )
        )

    def run_stage_guard(
        self,
        explanation: ExplainOutput,
        extracted_items: List[ExtractionOutputItem],
        request_id: Optional[str] = None,
    ) -> OutputGuardOutput:
        """Execute Stage 6: Layer 3 Output Guardrails & Numerical Verification."""
        req_id = request_id or generate_request_id()
        return self.stage_output_guard(
            OutputGuardInput(
                request_id=req_id,
                explanation=explanation,
                extracted_items=extracted_items,
            )
        )

    def run_modular_pipeline(
        self,
        file_bytes: bytes,
        filename: str,
        request_id: Optional[str] = None,
        explain_all: bool = False,
    ) -> OutputGuardOutput:
        """Execute all six stages sequentially in an independently verifiable chain with PII-safe tracing."""
        req_id = request_id or generate_request_id()

        with self.tracer.start_trace(
            "modular_pipeline", request_id=req_id, filename=filename
        ) as trace:
            # Stage 1: Validate upload
            with self.tracer.span("stage_1_validate", parent_trace=trace) as s_val:
                s_val.set_input(filename=filename, file_size_bytes=len(file_bytes))
                val_out = self.run_stage_validate(file_bytes, filename, req_id)
                s_val.set_output(is_valid=val_out.is_valid, mime_type=val_out.mime_type)
                if not val_out.is_valid:
                    raise ValueError(f"Upload validation failed: {val_out.error}")

            # Stage 2: OCR parse
            with self.tracer.span("stage_2_ocr", parent_trace=trace) as s_ocr:
                s_ocr.set_input(page_count=val_out.page_count)
                ocr_out = self.run_stage_ocr(val_out.sanitized_bytes, filename, req_id)
                total_lines = sum(len(p.lines) for p in ocr_out.pages)
                s_ocr.set_output(total_lines=total_lines, total_pages=ocr_out.total_pages)

            # Stage 3: Extract values with deterministic flags
            with self.tracer.span("stage_3_extract", parent_trace=trace) as s_ext:
                s_ext.set_input(total_pages=ocr_out.total_pages)
                ext_out = self.run_stage_extract(
                    ocr_out, raw_bytes=val_out.sanitized_bytes, request_id=req_id
                )
                flagged_count = sum(
                    1
                    for item in ext_out.items
                    if item.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
                )
                s_ext.set_output(
                    biomarkers_extracted=len(ext_out.items), flagged_count=flagged_count
                )

            # Stage 4: Knowledge retrieval
            with self.tracer.span("stage_4_retrieve", parent_trace=trace) as s_ret:
                queries = [
                    f"{item.test_name} {item.flag.value} lab test meaning" for item in ext_out.items
                ]
                s_ret.set_input(query_count=len(queries))
                ret_out = self.run_stage_retrieve(queries, req_id)
                s_ret.set_output(total_chunks=ret_out.total_chunks)

            # Stage 5: Explain synthesis
            with self.tracer.span("stage_5_explain", parent_trace=trace) as s_exp:
                s_exp.set_input(explain_all=explain_all, query_count=len(queries))
                exp_out = self.run_stage_explain(ext_out, ret_out, req_id, explain_all=explain_all)
                total_citations = sum(len(t.claims) for t in exp_out.test_explanations)
                s_exp.set_output(
                    explanations_count=len(exp_out.test_explanations),
                    citations_count=total_citations,
                )

            # Stage 6: Output guardrails & numerical check
            with self.tracer.span("stage_6_guard", parent_trace=trace) as s_grd:
                s_grd.set_input(test_count=len(exp_out.test_explanations))
                guard_out = self.run_stage_guard(exp_out, ext_out.items, req_id)
                s_grd.set_output(
                    is_safe=guard_out.is_safe,
                    violations=guard_out.violations_detected,
                    citation_accuracy=guard_out.citation_accuracy,
                )

            return guard_out

    def check_user_input(self, user_question: str) -> GuardrailResult:
        """Evaluate a user question against Layer 1 Input Guardrails."""
        return self.input_guard.check(user_question)

    def process_report(
        self,
        pdf_source: Union[str, Path, bytes, BinaryIO],
        user_question: Optional[str] = None,
        explain_all_tests: bool = False,
    ) -> ReportExplanation:
        """Process a laboratory PDF report end-to-end with distributed tracing."""
        with self.tracer.start_trace("process_report", explain_all=explain_all_tests) as trace:
            # Step 0: Check user question with Layer 1 Input Guard
            if user_question:
                with self.tracer.span("input_guard", trace) as s_guard:
                    s_guard.set_input(user_question=user_question)
                    guard_res = self.check_user_input(user_question)
                    s_guard.set_output(
                        blocked=guard_res.blocked, category=guard_res.violation_category
                    )
                    if guard_res.blocked:
                        return ReportExplanation(
                            report_summary_en=guard_res.safe_response_en,
                            report_summary_hi=guard_res.safe_response_hi,
                            test_explanations=[],
                            flagged_count=0,
                            total_tests=0,
                            disclaimer=self.config.guardrails.disclaimer.get("en", ""),
                        )

            # Step 1: 3-Tier PDF Extraction
            with self.tracer.span("extraction", trace) as s_extract:
                lab_report: LabReport = self.extractor.extract(pdf_source)
                s_extract.set_output(
                    method=lab_report.extraction_method,
                    total_tests=len(lab_report.tests),
                    patient_id=getattr(lab_report, "patient_id", "ANONYMIZED"),
                )

            return self._explain_single_lab_report(
                lab_report, explain_all_tests=explain_all_tests, trace=trace
            )

    def explain_lab_report(
        self,
        lab_report: LabReport,
        explain_all_tests: bool = False,
    ) -> ReportExplanation:
        """Process an already extracted/confirmed LabReport through flagging, RAG, and explanation synthesis."""
        with self.tracer.start_trace("explain_lab_report", explain_all=explain_all_tests) as trace:
            return self._explain_single_lab_report(
                lab_report, explain_all_tests=explain_all_tests, trace=trace
            )

    def _explain_single_lab_report(
        self,
        lab_report: LabReport,
        explain_all_tests: bool = False,
        trace=None,
    ) -> ReportExplanation:
        """Internal helper to flag, evaluate correlations, run RAG, and assemble explanation for a single report."""
        # Step 2A: LOINC Standard Ontology Mapping & Demographic Stratification
        lab_report = LOINCMapper.enrich_report(lab_report)
        lab_report = DemographicIntervalEngine.apply_demographic_stratification(lab_report)

        # Step 2B: Deterministic Flagging (pure code, zero LLM)
        flag_span = self.tracer.span("flagging", trace) if trace else None
        if flag_span:
            with flag_span as s_flag:
                lab_report = self.flagger.flag_report(lab_report)
                flagged_count = sum(
                    1
                    for t in lab_report.tests
                    if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
                )
                s_flag.set_output(flagged_count=flagged_count)
        else:
            lab_report = self.flagger.flag_report(lab_report)
            flagged_count = sum(
                1 for t in lab_report.tests if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
            )

        # Step 2B: Cross-Analyte Correlation Evaluation
        corr_span = self.tracer.span("correlations", trace) if trace else None
        if corr_span:
            with corr_span as s_corr:
                correlations = self.correlation_engine.evaluate(lab_report.tests)
                s_corr.set_output(correlations_count=len(correlations))
        else:
            correlations = self.correlation_engine.evaluate(lab_report.tests)

        # Step 2C: Panic Alerts, Drug Interferences, and Lifestyle Guidance
        panic_alerts = self.panic_engine.evaluate(lab_report.tests)
        interferences = self.interference_engine.evaluate(lab_report.tests)
        lifestyle_guidance = self.lifestyle_engine.evaluate(lab_report.tests)

        # Record in longitudinal history tracker
        self.history_tracker.add_report(lab_report)

        # Step 3 & 4: RAG Retrieval + Re-ranking and LLM Explanation (Concurrent Execution)
        tests_to_explain = [
            test
            for test in lab_report.tests
            if (test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)) or explain_all_tests
        ]

        def _process_single_analyte(test: TestResult) -> TestExplanation:
            query = f"{test.test_name} {test.flag.value} lab test meaning"

            # 3A & 3B: RAG
            rag_span = self.tracer.span(f"rag_{test.test_name}", trace) if trace else None
            if rag_span:
                with rag_span as s_rag:
                    candidates = self.retriever.retrieve(
                        query, top_k=self.config.rag.retrieval.top_k
                    )
                    reranked = self.reranker.rerank(
                        query, candidates, top_n=self.config.rag.reranker.top_n
                    )
                    s_rag.set_output(top_candidates=[c["id"] for c in reranked])
            else:
                candidates = self.retriever.retrieve(query, top_k=self.config.rag.retrieval.top_k)
                reranked = self.reranker.rerank(
                    query, candidates, top_n=self.config.rag.reranker.top_n
                )

            # 4: LLM Generation
            gen_span = self.tracer.span(f"generation_{test.test_name}", trace) if trace else None
            if gen_span:
                with gen_span as s_gen:
                    explanation = self.generator.explain_test(test, reranked)
                    in_tok = len(query.split()) * 4 + 400
                    out_tok = (
                        len(explanation.explanation_en.split())
                        + len(explanation.explanation_hi.split())
                    ) * 2
                    if trace:
                        trace.add_tokens(self.config.models.explanation_llm, in_tok, out_tok)
                    s_gen.set_output(sources_count=len(explanation.source_urls))
            else:
                explanation = self.generator.explain_test(test, reranked)

            # 5: Layer 3 Output Guardrail inspection and sanitization
            out_span = self.tracer.span(f"output_guard_{test.test_name}", trace) if trace else None
            if out_span:
                with out_span as s_outguard:
                    explanation = self.output_guard.check(explanation)
                    s_outguard.set_output(verified=True)
            else:
                explanation = self.output_guard.check(explanation)

            return explanation

        if len(tests_to_explain) <= 1:
            test_explanations = [_process_single_analyte(t) for t in tests_to_explain]
        else:
            max_workers = min(8, len(tests_to_explain))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                test_explanations = list(executor.map(_process_single_analyte, tests_to_explain))

        # Step 6: HIPAA PHI de-identification before assembling final report
        anonymized_report, phi_mapping = self.deidentifier.anonymize_lab_report(lab_report)
        if phi_mapping:
            self.audit_logger.log_event(
                event_type="PHI_DEIDENTIFIED",
                actor_id="system_pipeline",
                resource_id=lab_report.patient_name or "anonymous_report",
                details={"redacted_tokens": list(phi_mapping.keys())},
            )

        final_report = self.generator.explain_report(
            anonymized_report,
            test_explanations,
            correlations=correlations,
            panic_alerts=panic_alerts,
            interferences=interferences,
            lifestyle_guidance=lifestyle_guidance,
        )

        # Step 7: Local re-hydration of surrogate tokens for patient presentation
        if phi_mapping:
            final_report.patient_name = self.deidentifier.de_anonymize_text(
                final_report.patient_name or "", phi_mapping
            )
            final_report.report_summary_en, final_report.report_summary_hi = (
                self.deidentifier.de_anonymize_explanation(
                    final_report.report_summary_en,
                    final_report.report_summary_hi,
                    phi_mapping,
                )
            )

        return final_report

    def _merge_reports_for_single_patient(self, reports: List[LabReport]) -> LabReport:
        """Merge multiple reports known to belong to the SAME individual."""
        merged_tests: List[TestResult] = []
        seen_tests: Dict[str, int] = {}

        p_name = next((r.patient_name for r in reports if r.patient_name), None)
        p_age = next((r.patient_age for r in reports if r.patient_age), None)
        p_gender = next((r.patient_gender for r in reports if r.patient_gender), None)
        p_date = reports[-1].report_date or reports[0].report_date
        lab_names = ", ".join(dict.fromkeys(r.lab_name for r in reports if r.lab_name))

        for rep in reports:
            for test in rep.tests:
                norm_k = test.test_name.strip().lower()
                if norm_k in seen_tests:
                    idx = seen_tests[norm_k]
                    if merged_tests[idx].value is None and test.value is not None:
                        merged_tests[idx] = test
                else:
                    seen_tests[norm_k] = len(merged_tests)
                    merged_tests.append(test)

        merged_report = LabReport(
            patient_name=p_name,
            patient_age=p_age,
            patient_gender=p_gender,
            report_date=p_date,
            lab_name=lab_names or self.config.default_lab_name or "",
            tests=merged_tests,
            extraction_method=f"batch_merge({len(reports)}_docs)",
        )
        return self.flagger.flag_report(merged_report)

    def process_multiple_reports(
        self,
        file_sources: List[Union[str, Path, bytes, BinaryIO]],
        user_question: Optional[str] = None,
        explain_all_tests: bool = False,
    ) -> ReportExplanation:
        """Process multiple laboratory reports with patient identity verification and isolation."""
        if not file_sources:
            return ReportExplanation(
                report_summary_en="No reports provided.",
                report_summary_hi="कोई रिपोर्ट प्रदान नहीं की गई।",
                total_tests=0,
            )

        if len(file_sources) == 1:
            return self.process_report(file_sources[0], user_question, explain_all_tests)

        with self.tracer.start_trace("process_multiple_reports", count=len(file_sources)) as trace:
            extracted_reports: List[LabReport] = []
            for src in file_sources:
                rep = self.extractor.extract(src)
                if rep.tests:
                    rep = self.flagger.flag_report(rep)
                    extracted_reports.append(rep)

            if not extracted_reports:
                return ReportExplanation(
                    report_summary_en="Could not extract data from the uploaded files.",
                    report_summary_hi="अपलोड की गई फ़ाइलों से डेटा निकाला नहीं जा सका।",
                    total_tests=0,
                )

            # Check Patient Compatibility to Prevent Cross-Contamination
            from src.extraction.patient_matcher import group_reports_by_patient

            match_res = group_reports_by_patient(extracted_reports)

            if not match_res.is_single_patient:
                # MULTI-PATIENT CASE: Safely isolate into distinct patient profiles
                patient_profiles: Dict[str, ReportExplanation] = {}
                total_tests_all = 0
                total_flagged_all = 0

                for patient_label, cohort in match_res.patient_groups.items():
                    if len(cohort) == 1:
                        p_exp = self._explain_single_lab_report(
                            cohort[0], explain_all_tests=explain_all_tests, trace=trace
                        )
                    else:
                        merged_p = self._merge_reports_for_single_patient(cohort)
                        p_exp = self._explain_single_lab_report(
                            merged_p, explain_all_tests=explain_all_tests, trace=trace
                        )

                    patient_profiles[patient_label] = p_exp
                    total_tests_all += p_exp.total_tests
                    total_flagged_all += p_exp.flagged_count

                return ReportExplanation(
                    patient_name="Multiple Patients",
                    report_summary_en=match_res.warning_message_en or "Multiple patients detected.",
                    report_summary_hi=match_res.warning_message_hi
                    or "विभिन्न मरीजों की रिपोर्ट पाई गई।",
                    total_tests=total_tests_all,
                    flagged_count=total_flagged_all,
                    is_multi_patient=True,
                    patient_warning=match_res.warning_message_en,
                    patient_profiles=patient_profiles,
                )

            # SINGLE-PATIENT CASE: Safe to merge
            merged_report = self._merge_reports_for_single_patient(extracted_reports)
            return self._explain_single_lab_report(
                merged_report, explain_all_tests=explain_all_tests, trace=trace
            )

    def answer_question(
        self,
        question: str,
        patient_context: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Answer an educational user question with RAG, guardrails, and telemetry."""
        with self.tracer.start_trace("answer_question", question=question) as trace:
            # 1. Input Guardrail check
            with self.tracer.span("input_guard", trace) as s_guard:
                guard_res = self.check_user_input(question)
                s_guard.set_output(blocked=guard_res.blocked, category=guard_res.violation_category)
                if guard_res.blocked:
                    return {
                        "blocked": True,
                        "category": guard_res.violation_category,
                        "answer_en": guard_res.safe_response_en,
                        "answer_hi": guard_res.safe_response_hi,
                        "source_urls": [],
                        "disclaimer": self.config.guardrails.disclaimer.get("en", ""),
                        "elapsed_ms": trace.elapsed_ms,
                        "cost_usd": 0.0,
                    }

            # 2. RAG Retrieval & Re-ranking
            with self.tracer.span("rag_retrieval", trace) as s_rag:
                candidates = self.retriever.retrieve(
                    question, top_k=self.config.rag.retrieval.top_k
                )
                reranked = self.reranker.rerank(
                    question, candidates, top_n=self.config.rag.reranker.top_n
                )
                context_chunks = [c.get("text", "") for c in reranked if c.get("text")]
                source_urls: List[str] = []
                for c in reranked:
                    url = c.get("metadata", {}).get("source_url")
                    if url and url not in source_urls:
                        source_urls.append(url)
                s_rag.set_output(sources_found=len(source_urls))

            # 3. Generation with Conversational History
            with self.tracer.span("generation_qa", trace):
                history_text = ""
                if chat_history:
                    recent_turns = []
                    for turn in chat_history[-4:]:
                        role = "User" if turn.get("role") == "user" else "Assistant"
                        content = turn.get("content", "").strip()
                        if content:
                            recent_turns.append(f"{role}: {content}")
                    if recent_turns:
                        history_text = "Recent Conversation:\n" + "\n".join(recent_turns) + "\n\n"

                # De-identify patient context and user question before LLM prompt assembly
                anon_q_res = self.deidentifier.anonymize_text(question)
                anon_ctx_res = self.deidentifier.anonymize_text(patient_context or "")
                qa_phi_mapping = {**anon_q_res.entity_mapping, **anon_ctx_res.entity_mapping}
                if qa_phi_mapping:
                    self.audit_logger.log_event(
                        event_type="PHI_DEIDENTIFIED",
                        actor_id="qa_user",
                        resource_id="conversational_qa",
                        details={"redacted_tokens": list(qa_phi_mapping.keys())},
                    )

                augmented_parts = []
                if history_text:
                    augmented_parts.append(history_text)
                if anon_ctx_res.sanitized_text:
                    augmented_parts.append(f"Report Context:\n{anon_ctx_res.sanitized_text}")
                augmented_parts.append(f"Current Question: {anon_q_res.sanitized_text}")
                augmented_q = "\n\n".join(augmented_parts)

                ans_en, ans_hi = self.generator.answer_question(
                    augmented_q, context_chunks, source_urls
                )
                in_tok = len(augmented_q.split()) * 4 + 400
                out_tok = (len(ans_en.split()) + len(ans_hi.split())) * 2
                trace.add_tokens(self.config.models.explanation_llm, in_tok, out_tok)

            # 4. Output Guardrail sanitization
            with self.tracer.span("output_guard_qa", trace) as s_outguard:
                sanitized_en, v_en = self.output_guard.sanitize_text(ans_en, lang="en")
                sanitized_hi, v_hi = self.output_guard.sanitize_text(ans_hi, lang="hi")
                s_outguard.set_output(redactions=v_en + v_hi)

            # 5. Local re-hydration of surrogate tokens
            if qa_phi_mapping:
                sanitized_en = self.deidentifier.de_anonymize_text(sanitized_en, qa_phi_mapping)
                sanitized_hi = self.deidentifier.de_anonymize_text(sanitized_hi, qa_phi_mapping)

            return {
                "blocked": False,
                "category": None,
                "answer_en": sanitized_en,
                "answer_hi": sanitized_hi,
                "source_urls": source_urls,
                "disclaimer": self.config.guardrails.disclaimer.get("en", ""),
                "elapsed_ms": trace.elapsed_ms,
                "cost_usd": trace.total_cost_usd,
            }
