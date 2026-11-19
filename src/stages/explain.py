"""Stage 5: Bilingual Clinical Explanation Synthesis (explain).

Leverages Gemini LLM to synthesize empathetic, accessible patient explanations
grounded in retrieved clinical guidelines in both English and Hindi.
"""

from __future__ import annotations

import time
from typing import List

from src.config import get_config
from src.explainer.generator import ExplanationGenerator
from src.extraction.schema import FlagStatus
from src.stages.logger import get_stage_logger
from src.stages.schemas import ExplainInput, ExplainOutput, TestExplanationItem

logger = get_stage_logger("explain")


class ExplainStage:
    """Independently callable stage generating structured bilingual clinical explanations."""

    def __init__(self):
        self.config = get_config()
        self.generator = ExplanationGenerator()

    def __call__(self, inp: ExplainInput) -> ExplainOutput:
        return self.explain(inp)

    def explain(self, inp: ExplainInput) -> ExplainOutput:
        t0 = time.perf_counter()
        lab_report = inp.extraction.to_lab_report()

        tests_to_explain = [
            item for item in inp.extraction.items
            if (item.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)) or inp.explain_all
        ]

        explanations: List[TestExplanationItem] = []
        for item in tests_to_explain:
            query = f"{item.test_name} {item.flag.value} lab test meaning"
            relevant_chunks = inp.retrieved_knowledge.chunks_by_query.get(query, [])
            
            # Convert retrieved chunks into generator format
            evidence = [
                {
                    "id": c.chunk_id,
                    "text": c.text,
                    "source_url": c.source_url,
                    "score": c.score,
                }
                for c in relevant_chunks
            ]

            test_res = item.to_test_result()
            exp = self.generator.explain_test(test_res, evidence)

            explanations.append(
                TestExplanationItem(
                    test_name=item.test_name,
                    value_display=f"{item.value} {item.unit}".strip() if item.value is not None else item.raw_value,
                    flag=item.flag,
                    explanation_en=exp.explanation_en,
                    explanation_hi=exp.explanation_hi,
                    clinical_significance=getattr(exp, "clinical_significance", None),
                    source_urls=exp.source_urls,
                )
            )

        # Generate overarching patient report summary
        flagged_count = inp.extraction.flagged_count
        total_tests = len(inp.extraction.items)
        patient_name = inp.extraction.patient_name

        if flagged_count == 0:
            summary_en = (
                f"All {total_tests} laboratory parameters evaluated are within their standard reference intervals. "
                "Maintain healthy lifestyle habits and review these findings with your healthcare provider."
            )
            summary_hi = (
                f"जांचे गए सभी {total_tests} प्रयोगशाला पैरामीटर मानक संदर्भ सीमा के भीतर हैं। "
                "स्वस्थ जीवनशैली की आदतें बनाए रखें और इन परिणामों की समीक्षा अपने चिकित्सक के साथ करें।"
            )
        else:
            summary_en = (
                f"{flagged_count} of {total_tests} laboratory biomarkers fall outside standard clinical reference intervals. "
                "Consult your physician for personalized medical evaluation and clinical correlation."
            )
            summary_hi = (
                f"{total_tests} में से {flagged_count} बायोमार्कर मानक संदर्भ सीमा से बाहर हैं। "
                "व्यक्तिगत चिकित्सा परामर्श और मार्गदर्शन के लिए अपने चिकित्सक से संपर्क करें।"
            )

        disclaimer = self.config.guardrails.disclaimer.get("en", "")

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Clinical explanations generated",
            inp.request_id,
            {
                "explained_tests_count": len(explanations),
                "flagged_count": flagged_count,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return ExplainOutput(
            request_id=inp.request_id,
            patient_name=patient_name,
            summary_en=summary_en,
            summary_hi=summary_hi,
            test_explanations=explanations,
            flagged_count=flagged_count,
            total_tests=total_tests,
            disclaimer=disclaimer,
        )


def explain(inp: ExplainInput) -> ExplainOutput:
    """Functional convenience entrypoint for Stage 5."""
    return ExplainStage()(inp)
