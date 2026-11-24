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

# Verified clinical analyte knowledge base for concise offline interpretation
# Verified clinical analyte knowledge base for clear, patient-accessible interpretation
ANALYTE_KNOWLEDGE = {
    "cholesterol": (
        "Total Cholesterol measures the overall fats in your blood.",
        "कुल कोलेस्ट्रॉल आपके रक्त में समग्र वसा की मात्रा को मापता है।",
        "Higher levels can build up in blood vessels. Your doctor can help you review diet and heart wellness.",
        "उच्च स्तर रक्त वाहिकाओं में वसा जमाव से जुड़े हो सकते हैं। अपने डॉक्टर से आहार पर चर्चा करें।",
    ),
    "triglyceride": (
        "Triglycerides measure the main type of fat stored in your body.",
        "ट्राइग्लिसराइड्स शरीर में संचित मुख्य वसा के स्तर को मापते हैं।",
        "Higher levels often relate to meals and exercise. Your doctor can suggest healthy lifestyle steps.",
        "उच्च स्तर अक्सर खान-पान और शारीरिक गतिविधि से जुड़े होते हैं।",
    ),
    "hdl": (
        "HDL is called protective cholesterol. It helps clear extra fat from your blood.",
        "एचडीएल सुरक्षात्मक कोलेस्ट्रॉल है जो रक्त से अतिरिक्त वसा हटाने में मदद करता है।",
        "Higher numbers are healthy and help protect your heart.",
        "उच्च स्तर हृदय स्वास्थ्य के लिए लाभकारी और सुरक्षात्मक माने जाते हैं।",
    ),
    "ldl": (
        "LDL carries cholesterol to your body tissues.",
        "एलडीएल रक्तप्रवाह में वसा कणों को शरीर के ऊतकों तक पहुंचाता है।",
        "Higher levels can build up in artery walls. Your doctor can advise on heart wellness.",
        "उच्च स्तर धमनियों में वसा जमाव की संभावना को बढ़ा सकते हैं।",
    ),
    "hemoglobin": (
        "Hemoglobin is the protein in red blood cells that carries oxygen to your whole body.",
        "हीमोग्लोबिन लाल रक्त कोशिकाओं में मौजूद प्रोटीन है जो पूरे शरीर में ऑक्सीजन पहुंचाता है।",
        "Values outside normal limits affect how much oxygen your organs receive.",
        "असामान्य स्तर शरीर के अंगों तक ऑक्सीजन पहुंचाने की क्षमता में बदलाव को दर्शाते हैं।",
    ),
    "glucose": (
        "Blood Glucose measures the sugar in your blood, which gives your cells energy.",
        "ब्लड ग्लूकोज रक्त में शर्करा की मात्रा को मापता है, जो कोशिकाओं को ऊर्जा देती है।",
        "Values outside the normal range show how your body balances daily energy.",
        "सामान्य सीमा से बाहर परिणाम यह दर्शाते हैं कि शरीर ऊर्जा संतुलन को कैसे नियंत्रित कर रहा है।",
    ),
    "creatinine": (
        "Creatinine measures natural muscle waste that healthy kidneys filter from blood.",
        "क्रिएटिनिन मांसपेशियों का प्राकृतिक अपशिष्ट है जिसे स्वस्थ गुर्दे रक्त से छानते हैं।",
        "Values outside normal limits show how well your kidneys are filtering your blood.",
        "असामान्य परिणाम यह दर्शाते हैं कि गुर्दे अपशिष्ट साफ करने में कितने कुशल हैं।",
    ),
    "platelet": (
        "Platelets are tiny blood cells that help your blood clot and stop bleeding.",
        "प्लेटलेट्स रक्त की छोटी कोशिकाएं हैं जो रक्त का थक्का बनाने और रक्तस्राव रोकने में मदद करती हैं।",
        "Counts outside the normal range affect how quickly cuts and bruises heal.",
        "असामान्य संख्या चोट लगने पर रक्त के थक्के बनने की गति को प्रभावित कर सकती है।",
    ),
    "alt": (
        "ALT is an enzyme found mainly inside your liver cells.",
        "एएलटी (एसजीपीटी) मुख्य रूप से यकृत की कोशिकाओं में पाया जाने वाला एंजाइम है।",
        "Higher levels show that liver cells may be facing temporary stress or irritation.",
        "बढ़े हुए स्तर यह दर्शाते हैं कि यकृत कोशिकाएं अस्थायी तनाव का सामना कर सकती हैं।",
    ),
    "ast": (
        "AST is an enzyme found in liver and muscle cells.",
        "एएसटी (एसजीओटी) यकृत और मांसपेशियों की कोशिकाओं में पाया जाने वाला एंजाइम है।",
        "Higher levels can happen with liver stress or after heavy muscle exercise.",
        "बढ़े हुए स्तर यकृत तनाव या भारी व्यायाम के बाद भी देखे जा सकते हैं।",
    ),
    "tsh": (
        "TSH is a hormone made by your brain to help guide your thyroid gland.",
        "टीएसएच मस्तिष्क द्वारा निर्मित हार्मोन है जो थायरॉइड ग्रंथि को नियंत्रित करता है।",
        "Values outside the normal range show how your body is setting its energy pace.",
        "असामान्य स्तर शरीर की ऊर्जा गति और चयापचय संतुलन में बदलाव का संकेत देते हैं।",
    ),
    "alkaline": (
        "Alkaline Phosphatase is an enzyme found in your liver and bones.",
        "अल्केलाइन फॉस्फेटेस यकृत और हड्डियों में पाया जाने वाला एंजाइम है।",
        "Higher levels can relate to bone growth, healing, or liver bile flow.",
        "बढ़े हुए स्तर हड्डियों के विकास या पित्त प्रवाह से संबंधित हो सकते हैं।",
    ),
    "bun": (
        "Blood Urea Nitrogen measures waste from protein that your kidneys remove.",
        "ब्लड यूरिया नाइट्रोजन प्रोटीन अपशिष्ट को मापता है जिसे गुर्दे बाहर निकालते हैं।",
        "Higher levels often relate to low fluid intake, high protein, or kidney filtering.",
        "उच्च स्तर अक्सर कम पानी पीने या गुर्दे की छानने की गति से जुड़े होते हैं।",
    ),
    "bilirubin": (
        "Bilirubin is a natural yellow substance made when old red blood cells break down.",
        "बिलीरुबिन एक पीला पदार्थ है जो पुरानी लाल रक्त कोशिकाओं के टूटने से बनता है।",
        "Higher levels can cause yellowing of eyes and show how bile flows through the liver.",
        "उच्च स्तर आंखों में पीलापन ला सकते हैं और यकृत के पित्त प्रवाह को दर्शाते हैं।",
    ),
}


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
        """Deterministic, grounded concise explanation generator for offline and testing environments."""
        flag_str = test.flag.value
        val_str = f"{test.value} {test.unit}" if test.value is not None else test.raw_value
        ref_str = test.ref_raw or (
            f"{test.ref_low} - {test.ref_high}"
            if test.ref_low is not None and test.ref_high is not None
            else "standard reference interval"
        )

        name_lower = test.test_name.lower()
        matched = None
        for k, v in ANALYTE_KNOWLEDGE.items():
            if k in name_lower:
                matched = v
                break

        if matched:
            purpose_en, purpose_hi, finding_detail_en, finding_detail_hi = matched
            finding_en = f"Your observed result is {val_str}, categorized as {flag_str.upper()} against the reference range ({ref_str}). {finding_detail_en}"
            finding_hi = f"आपका परिणाम {val_str} है, जो संदर्भ सीमा ({ref_str}) के अनुसार {flag_str.upper()} की श्रेणी में आता है। {finding_detail_hi}"
        else:
            purpose_en = f"{test.test_name} measures a health indicator in your blood."
            purpose_hi = f"{test.test_name} आपके रक्त में एक महत्वपूर्ण स्वास्थ्य संकेतक को मापता है।"
            finding_en = f"Your result is {val_str}, noted as {flag_str.upper()} compared to the reference range ({ref_str}). Please discuss this finding with your physician."
            finding_hi = f"आपका परिणाम {val_str} है, जो संदर्भ सीमा ({ref_str}) के अनुसार {flag_str.upper()} की श्रेणी में आता है। कृपया अपने चिकित्सक से चर्चा करें।"

        summary_en = (
            f"• What It Measures: {purpose_en}\n• What This Finding Indicates: {finding_en}"
        )
        summary_hi = f"• यह जांच क्या मापती है: {purpose_hi}\n• आपके परिणाम का क्या अर्थ है: {finding_hi}"

        doctor_q = [
            f"What clinical factors might be contributing to my {test.test_name} result being {flag_str}?",
            "Are any follow-up tests, monitoring intervals, or lifestyle modifications recommended?",
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
                for fb in getattr(
                    self.config.models,
                    "fallback_models",
                    ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
                ):
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                for cand_model in models_to_try:
                    try:
                        # For single biomarker definitions, skip thinking tokens by default unless explicitly configured,
                        # avoiding 2-4 seconds of unnecessary reasoning latency per analyte.
                        test_thinking = os.environ.get("EXPLANATION_THINKING_TEST", "").lower() in (
                            "1",
                            "true",
                            "yes",
                        )
                        thinking_config = None
                        if (
                            test_thinking
                            and self.thinking_level
                            and (
                                "flash-lite" in cand_model.lower()
                                or "gemini-3" in cand_model.lower()
                                or "2.5" in cand_model.lower()
                            )
                        ):
                            try:
                                thinking_config = types.ThinkingConfig(
                                    thinking_level=self.thinking_level.upper()
                                )
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
                            logger.warning(
                                f"Gemini API model '{cand_model}' call error: {model_err}"
                            )
                            break

            except Exception as e:
                logger.warning(
                    f"Gemini API explanation generation failed: {e}. Falling back to offline generator."
                )

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
                for fb in getattr(
                    self.config.models,
                    "fallback_models",
                    ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
                ):
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                for cand_model in models_to_try:
                    try:
                        thinking_config = None
                        if self.thinking_level and (
                            "flash-lite" in cand_model.lower()
                            or "gemini-3" in cand_model.lower()
                            or "2.5" in cand_model.lower()
                        ):
                            try:
                                thinking_config = types.ThinkingConfig(
                                    thinking_level=self.thinking_level.upper()
                                )
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
                            logger.warning(
                                f"Gemini Q&A generation failed with '{cand_model}': {model_err}"
                            )
                            break

            except Exception as e:
                logger.warning(
                    f"Gemini Q&A generation failed: {e}. Falling back to offline synthesis."
                )

        # Offline synthesis using retrieved context
        top_context = (
            context_chunks[0]
            if context_chunks
            else "Laboratory tests provide objective physiological indicators."
        )
        clean_context = " ".join(top_context.split()[:50]) + "..."
        ans_en = (
            f"Based on clinical education guidelines: {clean_context} "
            "Please consult your primary care doctor for guidance tailored to your overall health."
        )
        ans_hi = (
            "चिकित्सीय दिशानिर्देशों के आधार पर: यह जांच शारीरिक स्वास्थ्य और संतुलन को दर्शाती है। "
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
        corr_note_en = (
            f" Additionally, {len(corr_list)} clinical ratio pattern(s) were analyzed ({elevated_corrs} flagged for discussion)."
            if corr_list
            else ""
        )
        corr_note_hi = (
            f" इसके अलावा, {len(corr_list)} नैदानिक अनुपातों का विश्लेषण किया गया है।" if corr_list else ""
        )

        panic_list = panic_alerts or []
        panic_prefix_en = (
            f"🚨 URGENT: {len(panic_list)} parameter(s) crossed critical medical panic thresholds requiring prompt clinician consultation. "
            if panic_list
            else ""
        )
        panic_prefix_hi = (
            f"🚨 तत्काल ध्यान: {len(panic_list)} परीक्षण परिणाम गंभीर आपातकालीन सीमा पार कर चुके हैं। "
            if panic_list
            else ""
        )

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
