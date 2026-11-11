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
from src.flagging.flagger import Flagger
from src.guardrails.input_guard import GuardrailResult, InputGuard
from src.guardrails.output_guard import OutputGuard
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

            # Step 2: Deterministic Flagging (pure code, zero LLM)
            with self.tracer.span("flagging", trace) as s_flag:
                lab_report = self.flagger.flag_report(lab_report)
                flagged_count = sum(
                    1 for t in lab_report.tests if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
                )
                s_flag.set_output(flagged_count=flagged_count)

            # Step 3 & 4: RAG Retrieval + Re-ranking and LLM Explanation
            test_explanations: List[TestExplanation] = []

            for test in lab_report.tests:
                is_flagged = test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
                if not is_flagged and not explain_all_tests:
                    continue

                query = f"{test.test_name} {test.flag.value} lab test meaning"

                # 3A & 3B: RAG
                with self.tracer.span(f"rag_{test.test_name}", trace) as s_rag:
                    candidates = self.retriever.retrieve(query, top_k=self.config.rag.retrieval.top_k)
                    reranked = self.reranker.rerank(query, candidates, top_n=self.config.rag.reranker.top_n)
                    s_rag.set_output(top_candidates=[c["id"] for c in reranked])

                # 4: LLM Generation
                with self.tracer.span(f"generation_{test.test_name}", trace) as s_gen:
                    explanation = self.generator.explain_test(test, reranked)
                    # Track estimated tokens for Flash-Lite
                    in_tok = len(query.split()) * 4 + 400
                    out_tok = (len(explanation.explanation_en.split()) + len(explanation.explanation_hi.split())) * 2
                    trace.add_tokens(self.config.models.explanation_llm, in_tok, out_tok)
                    s_gen.set_output(sources_count=len(explanation.source_urls))

                # 5: Layer 3 Output Guardrail inspection and sanitization
                with self.tracer.span(f"output_guard_{test.test_name}", trace) as s_outguard:
                    explanation = self.output_guard.check(explanation)
                    s_outguard.set_output(verified=True)

                test_explanations.append(explanation)

            # Step 6: Assemble final report explanation
            final_report = self.generator.explain_report(lab_report, test_explanations)
            return final_report
