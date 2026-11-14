"""Pipeline orchestrator unifying extraction, deterministic flagging, RAG, and guardrails."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Union

from src.config import get_config
from src.explainer.generator import ExplanationGenerator
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.router import ExtractionRouter
from src.extraction.schema import FlagStatus, LabReport
from src.flagging.correlations import CorrelationEngine
from src.flagging.flagger import Flagger
from src.guardrails.input_guard import GuardrailResult, InputGuard
from src.guardrails.output_guard import OutputGuard
from src.history.tracker import HistoryTracker
from src.rag.reranker import CrossEncoderReranker
from src.rag.retriever import ChromaRetriever
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
                    s_guard.set_output(blocked=guard_res.blocked, category=guard_res.violation_category)
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
                    patient=lab_report.patient_name,
                )

            return self._explain_single_lab_report(lab_report, explain_all_tests=explain_all_tests, trace=trace)

    def _explain_single_lab_report(
        self,
        lab_report: LabReport,
        explain_all_tests: bool = False,
        trace = None,
    ) -> ReportExplanation:
        """Internal helper to flag, evaluate correlations, run RAG, and assemble explanation for a single report."""
        # Step 2: Deterministic Flagging (pure code, zero LLM)
        flag_span = self.tracer.span("flagging", trace) if trace else None
        if flag_span:
            with flag_span as s_flag:
                lab_report = self.flagger.flag_report(lab_report)
                flagged_count = sum(
                    1 for t in lab_report.tests if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
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

        # Record in longitudinal history tracker
        self.history_tracker.add_report(lab_report)

        # Step 3 & 4: RAG Retrieval + Re-ranking and LLM Explanation
        test_explanations: List[TestExplanation] = []

        for test in lab_report.tests:
            is_flagged = test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
            if not is_flagged and not explain_all_tests:
                continue

            query = f"{test.test_name} {test.flag.value} lab test meaning"

            # 3A & 3B: RAG
            rag_span = self.tracer.span(f"rag_{test.test_name}", trace) if trace else None
            if rag_span:
                with rag_span as s_rag:
                    candidates = self.retriever.retrieve(query, top_k=self.config.rag.retrieval.top_k)
                    reranked = self.reranker.rerank(query, candidates, top_n=self.config.rag.reranker.top_n)
                    s_rag.set_output(top_candidates=[c["id"] for c in reranked])
            else:
                candidates = self.retriever.retrieve(query, top_k=self.config.rag.retrieval.top_k)
                reranked = self.reranker.rerank(query, candidates, top_n=self.config.rag.reranker.top_n)

            # 4: LLM Generation
            gen_span = self.tracer.span(f"generation_{test.test_name}", trace) if trace else None
            if gen_span:
                with gen_span as s_gen:
                    explanation = self.generator.explain_test(test, reranked)
                    in_tok = len(query.split()) * 4 + 400
                    out_tok = (len(explanation.explanation_en.split()) + len(explanation.explanation_hi.split())) * 2
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

            test_explanations.append(explanation)

        # Step 6: Assemble final report explanation with clinical correlations
        final_report = self.generator.explain_report(
            lab_report, test_explanations, correlations=correlations
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
            lab_name=lab_names or "Consolidated Diagnostic Services",
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
                        p_exp = self._explain_single_lab_report(cohort[0], explain_all_tests=explain_all_tests, trace=trace)
                    else:
                        merged_p = self._merge_reports_for_single_patient(cohort)
                        p_exp = self._explain_single_lab_report(merged_p, explain_all_tests=explain_all_tests, trace=trace)

                    patient_profiles[patient_label] = p_exp
                    total_tests_all += p_exp.total_tests
                    total_flagged_all += p_exp.flagged_count

                return ReportExplanation(
                    patient_name="Multiple Patients",
                    report_summary_en=match_res.warning_message_en or "Multiple patients detected.",
                    report_summary_hi=match_res.warning_message_hi or "विभिन्न मरीजों की रिपोर्ट पाई गई।",
                    total_tests=total_tests_all,
                    flagged_count=total_flagged_all,
                    is_multi_patient=True,
                    patient_warning=match_res.warning_message_en,
                    patient_profiles=patient_profiles,
                )

            # SINGLE-PATIENT CASE: Safe to merge
            merged_report = self._merge_reports_for_single_patient(extracted_reports)
            return self._explain_single_lab_report(merged_report, explain_all_tests=explain_all_tests, trace=trace)

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
                candidates = self.retriever.retrieve(question, top_k=self.config.rag.retrieval.top_k)
                reranked = self.reranker.rerank(question, candidates, top_n=self.config.rag.reranker.top_n)
                context_chunks = [c.get("text", "") for c in reranked if c.get("text")]
                source_urls: List[str] = []
                for c in reranked:
                    url = c.get("metadata", {}).get("source_url")
                    if url and url not in source_urls:
                        source_urls.append(url)
                s_rag.set_output(sources_found=len(source_urls))

            # 3. Generation with Conversational History
            with self.tracer.span("generation_qa", trace) as s_gen:
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

                augmented_parts = []
                if history_text:
                    augmented_parts.append(history_text)
                if patient_context:
                    augmented_parts.append(f"Report Context:\n{patient_context}")
                augmented_parts.append(f"Current Question: {question}")
                augmented_q = "\n\n".join(augmented_parts)

                ans_en, ans_hi = self.generator.answer_question(augmented_q, context_chunks, source_urls)
                in_tok = len(augmented_q.split()) * 4 + 400
                out_tok = (len(ans_en.split()) + len(ans_hi.split())) * 2
                trace.add_tokens(self.config.models.explanation_llm, in_tok, out_tok)

            # 4. Output Guardrail sanitization
            with self.tracer.span("output_guard_qa", trace) as s_outguard:
                sanitized_en, v_en = self.output_guard.sanitize_text(ans_en, lang="en")
                sanitized_hi, v_hi = self.output_guard.sanitize_text(ans_hi, lang="hi")
                s_outguard.set_output(redactions=v_en + v_hi)

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
