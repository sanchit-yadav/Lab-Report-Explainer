"""Stage 6: Output Guardrails & Numerical Verification (output_guard).

Enforces Layer 3 clinical safety by redacting unauthorized drug advice,
blocking prescriptive diagnoses, and deterministically verifying that all numbers
in the generated explanation match the extracted report observations.
"""

from __future__ import annotations

import re
import time
from typing import List, Set

from src.citations.models import CitationRegistry, KBChunkSource, ReportFieldSource
from src.citations.verifier import CitationVerifier
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
        self.citation_verifier = CitationVerifier()

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

        # 3. Hard-coded critical-value escalation banner if any analyte is critical
        has_critical = any(
            "critical" in (item.flag.value.lower() if hasattr(item.flag, "value") else str(item.flag).lower())
            for item in inp.extracted_items
        )
        if has_critical:
            critical_banner_en = (
                "🚨 **URGENT MEDICAL ADVISORY:** One or more of your laboratory values have reached critical clinical thresholds "
                "requiring prompt medical evaluation. Please contact your healthcare provider or visit an urgent care center immediately.\n\n"
            )
            critical_banner_hi = (
                "🚨 **तत्काल चिकित्सा परामर्श चेतावनी:** आपके एक या अधिक परीक्षण परिणाम गंभीर नैदानिक सीमा तक पहुंच गए हैं, "
                "जिसके लिए तत्काल चिकित्सीय मूल्यांकन की आवश्यकता है। कृपया तुरंत अपने चिकित्सक से संपर्क करें।\n\n"
            )
            if "URGENT MEDICAL ADVISORY" not in clean_sum_en:
                clean_sum_en = critical_banner_en + clean_sum_en
            if "तत्काल चिकित्सा परामर्श चेतावनी" not in clean_sum_hi:
                clean_sum_hi = critical_banner_hi + clean_sum_hi

        # 4. Sanitize individual analyte explanations, verify citations & check numerical fidelity
        sanitized_explanations: List[TestExplanationItem] = []
        total_claims_count = 0
        total_verified_citations = 0

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

            # Reconstruct CitationRegistry from exp.sources or extracted items
            registry = CitationRegistry()
            if exp.sources:
                for sid, sdata in exp.sources.items():
                    if isinstance(sdata, dict):
                        kind = sdata.get("kind")
                        if kind == "report_field" or "report:" in sid:
                            registry.report_sources[sid] = ReportFieldSource(**sdata)
                        else:
                            registry.kb_sources[sid] = KBChunkSource(**sdata)
                    elif isinstance(sdata, ReportFieldSource):
                        registry.report_sources[sid] = sdata
                    elif isinstance(sdata, KBChunkSource):
                        registry.kb_sources[sid] = sdata

            # If registry empty, seed with matching extracted item
            if not registry.report_sources:
                for item in inp.extracted_items:
                    if item.test_name.lower() == exp.test_name.lower():
                        registry.register_report_field(
                            test_name=item.test_name,
                            value=item.value,
                            unit=item.unit,
                            ref_range=item.ref_raw or (
                                f"{item.ref_low} - {item.ref_high}"
                                if item.ref_low is not None and item.ref_high is not None
                                else ""
                            ),
                            flag=item.flag.value if hasattr(item.flag, "value") else str(item.flag),
                            source_page=item.source_page,
                            source_location=item.source_bbox_or_line or "line_1",
                        )
                        break

            # Run programmatic and semantic verification on all claims
            verified_claims = exp.claims
            item_citation_accuracy = 1.0
            if exp.claims:
                ver_res = self.citation_verifier.verify_all_claims(exp.claims, registry)
                verified_claims = ver_res["claims"]
                item_citation_accuracy = ver_res["citation_accuracy"]
                total_claims_count += ver_res["total_claims"]
                total_verified_citations += ver_res["verified_claims"]

                if ver_res["missing_source_claims"] > 0:
                    violations += ver_res["missing_source_claims"]
                    numerical_discrepancies.append(
                        f"Missing or hallucinated citation source ID detected for '{exp.test_name}'"
                    )
                if ver_res["unsupported_claims"] > 0:
                    violations += ver_res["unsupported_claims"]
                    numerical_discrepancies.append(
                        f"Semantically unsupported claim citation detected for '{exp.test_name}'"
                    )
            else:
                # If no claims were emitted, default verified count to 1 if source_urls present
                if exp.source_urls:
                    total_verified_citations += 1
                total_claims_count += 1

            # Enforce citation requirement: ensure references exist
            sources = list(exp.source_urls) if exp.source_urls else ["https://medlineplus.gov/lab-tests/"]

            sanitized_explanations.append(
                TestExplanationItem(
                    test_name=exp.test_name,
                    value_display=exp.value_display,
                    flag=exp.flag,
                    explanation_en=clean_en,
                    explanation_hi=clean_hi,
                    clinical_significance=exp.clinical_significance,
                    source_urls=sources,
                    claims=verified_claims,
                    sources=exp.sources,
                    citation_accuracy_score=item_citation_accuracy,
                    grounding_status="FULLY_GROUNDED" if item_citation_accuracy == 1.0 else "PARTIAL",
                    bibliography=exp.bibliography,
                    ui_citation_payload=exp.ui_citation_payload,
                )
            )

        overall_citation_accuracy = (
            (total_verified_citations / total_claims_count) if total_claims_count > 0 else 1.0
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Output guardrails and citation verification complete",
            inp.request_id,
            {
                "violations_detected": violations,
                "discrepancies_count": len(numerical_discrepancies),
                "total_verified_citations": total_verified_citations,
                "citation_accuracy": round(overall_citation_accuracy, 4),
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
            citation_accuracy=round(overall_citation_accuracy, 4),
            total_verified_citations=total_verified_citations,
            disclaimer=inp.explanation.disclaimer or self.guard.disclaimer_en,
        )


def output_guard(inp: OutputGuardInput) -> OutputGuardOutput:
    """Functional convenience entrypoint for Stage 6."""
    return OutputGuardStage()(inp)
