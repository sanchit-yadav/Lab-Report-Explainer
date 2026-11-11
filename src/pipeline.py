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

logger = logging.getLogger("pipeline")


class LabReportPipeline:
    """End-to-end orchestration pipeline for the AI Lab Report Explainer."""

    def __init__(self):
        self.config = get_config()
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
        """Process a laboratory PDF report end-to-end.

        Args:
            pdf_source: File path, bytes, or file-like object of the lab report PDF.
            user_question: Optional user query submitted alongside the report.
            explain_all_tests: If True, explains all tests; if False, prioritizes flagged tests.

        Returns:
            ReportExplanation instance containing structured summaries and per-test explanations.
        """
        # Step 0: Check user question with Layer 1 Input Guard
        if user_question:
            guard_res = self.check_user_input(user_question)
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
        logger.info("Executing 3-tier PDF extraction...")
        lab_report: LabReport = self.extractor.extract(pdf_source)

        # Step 2: Deterministic Flagging (pure code, zero LLM)
        logger.info(f"Deterministically flagging {len(lab_report.tests)} extracted tests...")
        lab_report = self.flagger.flag_report(lab_report)

        # Step 3 & 4: RAG Retrieval + Re-ranking and LLM Explanation
        test_explanations: List[TestExplanation] = []

        for test in lab_report.tests:
            # Decide whether to explain this test
            is_flagged = test.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
            if not is_flagged and not explain_all_tests:
                continue

            query = f"{test.test_name} {test.flag.value} lab test meaning"

            # 3A: Vector search
            candidates = self.retriever.retrieve(query, top_k=self.config.rag.retrieval.top_k)

            # 3B: Cross-Encoder Re-ranking
            reranked = self.reranker.rerank(query, candidates, top_n=self.config.rag.reranker.top_n)

            # 4: LLM Generation
            explanation = self.generator.explain_test(test, reranked)

            # 5: Layer 3 Output Guardrail inspection and sanitization
            explanation = self.output_guard.check(explanation)

            test_explanations.append(explanation)

        # Step 6: Assemble final report explanation
        final_report = self.generator.explain_report(lab_report, test_explanations)
        return final_report
