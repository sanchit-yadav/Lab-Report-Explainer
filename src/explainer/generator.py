"""Explanation generator leveraging Gemini 3.1 Flash-Lite with structured output."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from src.config import get_config
from src.explainer.prompts import build_explanation_prompt, get_system_prompt
from src.explainer.schema import ReportExplanation, TestExplanation
from src.extraction.schema import FlagStatus, LabReport, TestResult
from src.flagging.correlations import ClinicalCorrelation
from src.flagging.interferences import DrugLabInterference
from src.flagging.lifestyle import LifestyleGuidance
from src.flagging.panic_values import PanicAlert

logger = logging.getLogger("generator")


class ExplanationGenerator:
    """Generates patient-friendly bilingual explanations using Gemini 3.1 Flash-Lite."""

    def __init__(self):
        self.config = get_config()
        self.model_name = self.config.models.explanation_llm
        self.thinking_level = self.config.models.explanation_thinking_level
        self.temperature = self.config.generation.temperature
        self.api_key = os.environ.get("GEMINI_API_KEY") or self.config.gemini_api_key

    def _generate_mock_explanation(
        self,
        test: TestResult,
        context_chunks: List[str],
        source_urls: List[str],
    ) -> TestExplanation:
        """Deterministic, grounded explanation generator for offline testing."""
        flag_str = test.flag.value
        val_str = f"{test.value} {test.unit}" if test.value is not None else test.raw_value

        summary_en = (
            f"This test measures {test.test_name}. Your observed level is {val_str}, "
            f"which is categorized as {flag_str.upper()} based on the reference range {test.ref_raw or 'provided'}. "
            "In general medical practice, this analyte helps assess organ function and overall physiological balance."
        )
        summary_hi = (
            f"यह जांच {test.test_name} के स्तर को मापती है। आपका परिणाम {val_str} है, "
            f"जो मानक संदर्भ सीमा के अनुसार {flag_str.upper()} की श्रेणी में आता है। "
            "चिकित्सीय संदर्भ में यह जांच शारीरिक संतुलन और अंग कार्यप्रणाली को समझने में सहायता करती है।"
        )

        doctor_q = [
            f"What might be contributing to my {test.test_name} result being {flag_str}?",
            f"Are there any follow-up tests or repeat evaluations recommended?",
            f"Should any dietary or medication adjustments be considered based on this finding?",
        ]

        return TestExplanation(
            test_name=test.test_name,
            flag=test.flag,
            explanation_en=summary_en,
            explanation_hi=summary_hi,
            source_urls=source_urls,
            doctor_questions=doctor_q,
            disclaimer="⚠️ This explanation is for educational purposes only. Please discuss with your doctor.",
        )

    def explain_test(
        self,
        test: TestResult,
        candidates: List[Dict[str, Any]],
    ) -> TestExplanation:
        """Generate structured bilingual explanation for a single test analyte."""
        context_chunks = [c.get("text", "") for c in candidates if c.get("text")]
        source_urls: List[str] = []
        for c in candidates:
            url = c.get("metadata", {}).get("source_url")
            if url and url not in source_urls:
                source_urls.append(url)

        # Use Gemini API if configured
        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                prompt = build_explanation_prompt(test, context_chunks, source_urls)
                system_prompt = get_system_prompt()

                models_to_try = [self.model_name]
                for fb in getattr(self.config.models, "fallback_models", ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]):
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                for cand_model in models_to_try:
                    try:
                        thinking_config = None
                        if self.thinking_level and ("flash-lite" in cand_model.lower() or "gemini-3" in cand_model.lower() or "2.5" in cand_model.lower()):
                            try:
                                thinking_config = types.ThinkingConfig(thinking_level=self.thinking_level.upper())
                            except Exception:
                                pass

                        config_kwargs = dict(
                            system_instruction=system_prompt,
                            temperature=self.temperature,
                            response_mime_type="application/json",
                            response_schema=TestExplanation,
                        )
                        if thinking_config is not None:
                            config_kwargs["thinking_config"] = thinking_config

                        response = client.models.generate_content(
                            model=cand_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(**config_kwargs),
                        )

                        if response.text:
                            clean_text = response.text.strip()
                            if clean_text.startswith("```"):
                                clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                                clean_text = re.sub(r"\s*```$", "", clean_text)
                            match = re.search(r"\{[\s\S]*\}", clean_text)
                            if match:
                                clean_text = match.group(0)
                            parsed = json.loads(clean_text)
                            return TestExplanation(**parsed)

                    except Exception as model_err:
                        err_str = str(model_err)
                        if any(c in err_str for c in ("503", "UNAVAILABLE", "high demand", "429")):
                            logger.warning(
                                f"Gemini model '{cand_model}' temporarily unavailable (503 / high demand). Trying next candidate..."
                            )
                            time.sleep(0.5)
                            continue
                        else:
                            logger.warning(f"Gemini API model '{cand_model}' call error: {model_err}")
                            break

            except Exception as e:
                logger.warning(f"Gemini API explanation generation failed: {e}. Falling back to offline generator.")

        # Offline / fallback mode
        return self._generate_mock_explanation(test, context_chunks, source_urls)

    def answer_question(
        self,
        question: str,
        context_chunks: List[str],
        source_urls: List[str],
    ) -> Tuple[str, str]:
        """Generate bilingual educational answer for an open user query."""
        if self.api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                system_prompt = get_system_prompt()
                prompt = (
                    f"User Question: {question}\n\n"
                    f"Clinical Context Guidelines:\n"
                    + "\n---\n".join(context_chunks[:3])
                    + "\n\nProvide an educational, clear response in both English and Hindi. "
                    "Do NOT diagnose any illness or prescribe medications. Refer to a physician for personalized care.\n"
                    "Output JSON with keys: 'answer_en' and 'answer_hi'."
                )

                models_to_try = [self.model_name]
                for fb in getattr(self.config.models, "fallback_models", ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]):
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                for cand_model in models_to_try:
                    try:
                        thinking_config = None
                        if self.thinking_level and ("flash-lite" in cand_model.lower() or "gemini-3" in cand_model.lower() or "2.5" in cand_model.lower()):
                            try:
                                thinking_config = types.ThinkingConfig(thinking_level=self.thinking_level.upper())
                            except Exception:
                                pass

                        qa_config_kwargs = dict(
                            system_instruction=system_prompt,
                            temperature=self.temperature,
                            response_mime_type="application/json",
                        )
                        if thinking_config is not None:
                            qa_config_kwargs["thinking_config"] = thinking_config

                        response = client.models.generate_content(
                            model=cand_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(**qa_config_kwargs),
                        )
                        if response.text:
                            clean_text = response.text.strip()
                            if clean_text.startswith("```"):
                                clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                                clean_text = re.sub(r"\s*```$", "", clean_text)
                            match = re.search(r"\{[\s\S]*\}", clean_text)
                            if match:
                                clean_text = match.group(0)
                            parsed = json.loads(clean_text)
                            return parsed.get("answer_en", ""), parsed.get("answer_hi", "")

                    except Exception as model_err:
                        err_str = str(model_err)
                        if any(c in err_str for c in ("503", "UNAVAILABLE", "high demand", "429")):
                            logger.warning(
                                f"Gemini Q&A model '{cand_model}' temporarily unavailable. Trying next candidate..."
                            )
                            time.sleep(0.5)
                            continue
                        else:
                            logger.warning(f"Gemini Q&A generation failed with '{cand_model}': {model_err}")
                            break

            except Exception as e:
                logger.warning(f"Gemini Q&A generation failed: {e}. Falling back to offline synthesis.")

        # Offline synthesis using retrieved context
        top_context = context_chunks[0] if context_chunks else "Laboratory tests provide objective physiological indicators."
        clean_context = " ".join(top_context.split()[:50]) + "..."
        ans_en = (
            f"Based on clinical education guidelines: {clean_context} "
            "Please consult your primary care doctor for guidance tailored to your overall health."
        )
        ans_hi = (
            f"चिकित्सीय दिशानिर्देशों के आधार पर: यह जांच शारीरिक स्वास्थ्य और संतुलन को दर्शाती है। "
            "कृपया अपने संपूर्ण स्वास्थ्य और उपचार के लिए अपने डॉक्टर से परामर्श अवश्य करें।"
        )
        return ans_en, ans_hi

    def explain_report(
        self,
        report: LabReport,
        test_explanations: List[TestExplanation],
        correlations: Optional[List[ClinicalCorrelation]] = None,
        panic_alerts: Optional[List[PanicAlert]] = None,
        interferences: Optional[List[DrugLabInterference]] = None,
        lifestyle_guidance: Optional[List[LifestyleGuidance]] = None,
    ) -> ReportExplanation:
        """Assemble an executive report summary aggregating all test explanations, clinical correlations, and panic alerts."""
        total = len(report.tests)
        flagged = sum(
            1 for t in report.tests if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
        )

        corr_list = correlations or []
        elevated_corrs = sum(1 for c in corr_list if c.severity != "normal")
        corr_note_en = f" Additionally, {len(corr_list)} clinical ratio pattern(s) were analyzed ({elevated_corrs} flagged for discussion)." if corr_list else ""
        corr_note_hi = f" इसके अलावा, {len(corr_list)} नैदानिक अनुपातों का विश्लेषण किया गया है।" if corr_list else ""

        panic_list = panic_alerts or []
        panic_prefix_en = f"🚨 URGENT: {len(panic_list)} parameter(s) crossed critical medical panic thresholds requiring prompt clinician consultation. " if panic_list else ""
        panic_prefix_hi = f"🚨 तत्काल ध्यान: {len(panic_list)} परीक्षण परिणाम गंभीर आपातकालीन सीमा पार कर चुके हैं। " if panic_list else ""

        summary_en = (
            f"{panic_prefix_en}Laboratory report summary for {report.patient_name or 'the patient'}. "
            f"A total of {total} test parameter(s) were analyzed, with {flagged} parameter(s) "
            f"outside standard reference intervals requiring clinical review.{corr_note_en}"
        )
        summary_hi = (
            f"{panic_prefix_hi}{report.patient_name or 'मरीज'} की लैब जांच रिपोर्ट का सारांश। "
            f"कुल {total} परीक्षणों का विश्लेषण किया गया, जिनमें से {flagged} परिणाम "
            f"मानक संदर्भ सीमा से बाहर पाए गए हैं जिन पर डॉक्टर से परामर्श आवश्यक है।{corr_note_hi}"
        )

        return ReportExplanation(
            patient_name=report.patient_name,
            report_date=report.report_date,
            report_summary_en=summary_en,
            report_summary_hi=summary_hi,
            test_explanations=test_explanations,
            flagged_count=flagged,
            total_tests=total,
            raw_report=report,
            correlations=corr_list,
            panic_alerts=panic_list,
            interferences=interferences or [],
            lifestyle_guidance=lifestyle_guidance or [],
        )
