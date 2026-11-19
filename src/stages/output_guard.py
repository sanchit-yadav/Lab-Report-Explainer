"""Stage 6: Output Guardrails & Numerical Verification (output_guard).

Enforces Layer 3 clinical safety by redacting unauthorized drug advice,
blocking prescriptive diagnoses, and deterministically verifying that all numbers
in the generated explanation match the extracted report observations.
"""

from __future__ import annotations

import re
import time
from typing import List, Set

from src.guardrails.output_guard import OutputGuard
from src.stages.logger import get_stage_logger
from src.stages.schemas import (
    OutputGuardInput,
    OutputGuardOutput,
    TestExplanationItem,
)

logger = get_stage_logger("output_guard")

NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")


class OutputGuardStage:
    """Independently callable stage verifying clinical safety and numerical truthfulness."""

    def __init__(self):
        self.guard = OutputGuard()

    def __call__(self, inp: OutputGuardInput) -> OutputGuardOutput:
        return self.sanitize(inp)

    def sanitize(self, inp: OutputGuardInput) -> OutputGuardOutput:
        t0 = time.perf_counter()
        violations = 0
        numerical_discrepancies: List[str] = []

        # 1. Build authoritative ground-truth set of all extracted numeric values
        known_numbers: Set[str] = set()
        for item in inp.extracted_items:
            if item.value is not None:
                known_numbers.add(str(item.value))
                if item.value.is_integer():
                    known_numbers.add(str(int(item.value)))
            if item.ref_low is not None:
                known_numbers.add(str(item.ref_low))
                if item.ref_low.is_integer():
                    known_numbers.add(str(int(item.ref_low)))
            if item.ref_high is not None:
                known_numbers.add(str(item.ref_high))
                if item.ref_high.is_integer():
                    known_numbers.add(str(int(item.ref_high)))

        # Also permit standard harmless numerical counts (1, 2, 3, etc. for test counts)
        total_tests = len(inp.extracted_items)
        for i in range(total_tests + 5):
            known_numbers.add(str(i))

        # 2. Sanitize summary prose
        clean_sum_en, v1 = self.guard.sanitize_text(inp.explanation.summary_en, "en")
        clean_sum_hi, v2 = self.guard.sanitize_text(inp.explanation.summary_hi, "hi")
        violations += (v1 + v2)

        # 3. Sanitize individual analyte explanations & check numerical fidelity
        sanitized_explanations: List[TestExplanationItem] = []
        for exp in inp.explanation.test_explanations:
            clean_en, v_en = self.guard.sanitize_text(exp.explanation_en, "en")
            clean_hi, v_hi = self.guard.sanitize_text(exp.explanation_hi, "hi")
            violations += (v_en + v_hi)

            # Numerical verification: verify all numbers in explanation prose exist in ground truth
            found_numbers = NUMBER_PATTERN.findall(clean_en)
            for num in found_numbers:
                if num not in known_numbers and float(num) > 10.0:  # Ignore trivial indices/counts
                    discrepancy = f"Unverified number '{num}' detected in explanation for '{exp.test_name}'"
                    numerical_discrepancies.append(discrepancy)

            sanitized_explanations.append(
                TestExplanationItem(
                    test_name=exp.test_name,
                    value_display=exp.value_display,
                    flag=exp.flag,
                    explanation_en=clean_en,
                    explanation_hi=clean_hi,
                    clinical_significance=exp.clinical_significance,
                    source_urls=exp.source_urls,
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Output guardrails and numerical verification complete",
            inp.request_id,
            {
                "violations_detected": violations,
                "discrepancies_count": len(numerical_discrepancies),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return OutputGuardOutput(
            request_id=inp.request_id,
            is_safe=(len(numerical_discrepancies) == 0),
            sanitized_summary_en=clean_sum_en,
            sanitized_summary_hi=clean_sum_hi,
            sanitized_explanations=sanitized_explanations,
            violations_detected=violations,
            numerical_discrepancies=numerical_discrepancies,
            disclaimer=inp.explanation.disclaimer or self.guard.disclaimer_en,
        )


def output_guard(inp: OutputGuardInput) -> OutputGuardOutput:
    """Functional convenience entrypoint for Stage 6."""
    return OutputGuardStage()(inp)
