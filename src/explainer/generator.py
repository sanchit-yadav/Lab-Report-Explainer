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
ANALYTE_KNOWLEDGE = {
    "cholesterol": (
        "Total Cholesterol evaluates the cumulative circulating lipid and lipoprotein particles in your bloodstream.",
        "कुल कोलेस्ट्रॉल आपके रक्तप्रवाह में मौजूद समग्र लिपिड और लिपोप्रोटीन कणों की मात्रा को मापता है।",
        "Elevated levels reflect higher circulating lipid density associated with arterial lipid deposition.",
        "बढ़े हुए स्तर रक्त वाहिकाओं में वसा के जमाव और परिसंचरण संबंधी जोखिम से जुड़े होते हैं।",
    ),
    "triglyceride": (
        "Triglycerides evaluate the primary chemical form of circulating fatty acids stored in body fat.",
        "ट्राइग्लिसराइड्स शरीर में संचित वसा और रक्त में मौजूद मुख्य वसायुक्त अम्लों के स्तर का मूल्यांकन करते हैं।",
        "Elevated levels correlate with dietary lipid intake, metabolic regulation, and cardiovascular risk factors.",
        "उच्च स्तर अक्सर आहार वसा, चयापचय नियमन और हृदय संबंधी जोखिम कारकों से जुड़े होते हैं।",
    ),
    "hdl": (
        "HDL (High-Density Lipoprotein) measures the 'protective' cholesterol that transports excess lipids from tissues back to the liver.",
        "एचडीएल सुरक्षात्मक कोलेस्ट्रॉल है जो अतिरिक्त वसा को ऊतकों से वापस यकृत में स्थानांतरित करने का कार्य करता है।",
        "Higher levels are physiologically desirable; reduced concentrations suggest diminished reverse lipid clearance.",
        "उचित स्तर सुरक्षात्मक माने जाते हैं; कम स्तर ऊतकों से वसा निकासी में कमी का संकेत दे सकते हैं।",
    ),
    "ldl": (
        "LDL (Low-Density Lipoprotein) measures circulating particles that carry cholesterol directly to peripheral tissues and arteries.",
        "एलडीएल रक्तप्रवाह में वसा कणों को ऊतकों और धमनियों तक ले जाने का कार्य करता है।",
        "Elevated levels indicate higher availability of circulating lipid particles prone to vascular deposition.",
        "उच्च स्तर धमनियों की दीवारों पर लिपिड संचय की संभावना को बढ़ाते हैं।",
    ),
    "hemoglobin": (
        "Hemoglobin is the iron-rich protein in red blood cells that transports oxygen from your lungs to tissues throughout your body.",
        "हीमोग्लोबिन लाल रक्त कोशिकाओं में मौजूद वह प्रोटीन है जो फेफड़ों से शरीर के सभी अंगों तक ऑक्सीजन पहुंचाता है।",
        "Deviations reflect alterations in cellular oxygen-carrying capacity and red blood cell production.",
        "असामान्य स्तर शरीर के ऊतकों तक ऑक्सीजन पहुंचाने की क्षमता में कमी या बदलाव को दर्शाते हैं।",
    ),
    "glucose": (
        "Blood Glucose measures the concentration of simple sugar circulating in your blood, the primary cellular energy source.",
        "ब्लड ग्लूकोज रक्त में मौजूद शर्करा की मात्रा को मापता है, जो शरीर की कोशिकाओं का मुख्य ऊर्जा स्रोत है।",
        "Values outside standard intervals reflect altered cellular glucose uptake and metabolic regulation.",
        "सामान्य सीमा से बाहर परिणाम यह दर्शाते हैं कि शरीर कोशिकाओं में ग्लूकोज को कितनी कुशलता से नियंत्रित कर रहा है।",
    ),
    "creatinine": (
        "Creatinine is a normal metabolic byproduct of muscle activity that is filtered continuously from blood by healthy kidneys.",
        "क्रिएटिनिन मांसपेशियों की सामान्य क्रियाशीलता का उप-उत्पाद है जिसे स्वस्थ गुर्दे रक्त से लगातार छानते हैं।",
        "Deviations from standard limits provide a direct indicator of renal filtration efficiency.",
        "सीमा से बाहर परिणाम यह दर्शाते हैं कि गुर्दे रक्त को साफ करने और अपशिष्ट निकालने में कितने सक्षम हैं।",
    ),
    "platelet": (
        "Platelets are specialized cell fragments essential for normal blood clotting and vascular repair.",
        "प्लेटलेट्स रक्त के थक्के जमने और रक्त वाहिकाओं की मरम्मत के लिए आवश्यक कोशिका अंश हैं।",
        "Out-of-range counts reflect changes in bone marrow production, consumption, or immune clearance.",
        "असामान्य संख्या प्लेटलेट उत्पादन, उपयोग या प्रतिरक्षा निकासी में परिवर्तन का संकेत देती है।",
    ),
    "alt": (
        "ALT (Alanine Aminotransferase) is an intracellular enzyme found predominantly in liver cells.",
        "एएलटी (एसजीपीटी) मुख्य रूप से यकृत की कोशिकाओं में पाया जाने वाला एक महत्वपूर्ण एंजाइम है।",
        "Elevated levels indicate increased cellular leakage into the bloodstream, reflecting hepatic physiological stress.",
        "बढ़े हुए स्तर यकृत कोशिकाओं से रक्त में एंजाइम के रिसाव और तनाव को दर्शाते हैं।",
    ),
    "ast": (
        "AST (Aspartate Aminotransferase) is an enzyme found in liver, heart, and muscle tissue supporting amino acid metabolism.",
        "एएसटी (एसजीओटी) यकृत, हृदय और मांसपेशियों के ऊतकों में पाया जाने वाला आवश्यक एंजाइम है।",
        "Changes in circulating activity reflect cellular turnover in metabolically active organ tissues.",
        "रक्त में इसका स्तर यकृत और अन्य सक्रिय अंगों में कोशिकीय बदलावों को दर्शाता है।",
    ),
    "tsh": (
        "TSH (Thyroid Stimulating Hormone) is produced by the pituitary gland to regulate thyroid hormone synthesis.",
        "टीएसएच पिट्यूटरी ग्रंथि द्वारा निर्मित हार्मोन है जो थायरॉइड ग्रंथि के कार्य को नियंत्रित करता है।",
        "Deviations from reference ranges reflect pituitary feedback regulation of systemic metabolic rate.",
        "असामान्य स्तर शरीर की चयापचय दर और थायरॉइड संतुलन में बदलाव का संकेत देते हैं।",
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
        ref_str = test.ref_raw or (f"{test.ref_low} - {test.ref_high}" if test.ref_low is not None and test.ref_high is not None else "standard reference interval")

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
            purpose_en = f"{test.test_name} is a clinical biomarker used to assess specific physiological pathways and metabolic status."
            purpose_hi = f"{test.test_name} एक नैदानिक बायोमार्कर है जो विशिष्ट शारीरिक कार्यप्रणाली और संतुलन का मूल्यांकन करता है।"
            finding_en = f"Your observed result is {val_str}, categorized as {flag_str.upper()} relative to standard reference limits ({ref_str}). Results outside standard intervals warrant review in the context of your overall clinical history."
            finding_hi = f"आपका परिणाम {val_str} है, जो संदर्भ सीमा ({ref_str}) के अनुसार {flag_str.upper()} की श्रेणी में आता है। मानक सीमा से बाहर परिणाम आपके समग्र स्वास्थ्य संदर्भ में समीक्षा की आवश्यकता दर्शाते हैं।"

        summary_en = (
            f"• What It Measures: {purpose_en}\n"
            f"• What This Finding Indicates: {finding_en}"
        )
        summary_hi = (
            f"• यह जांच क्या मापती है: {purpose_hi}\n"
            f"• आपके परिणाम का क्या अर्थ है: {finding_hi}"
        )

        doctor_q = [
            f"What clinical factors might be contributing to my {test.test_name} result being {flag_str}?",
            f"Are any follow-up tests, monitoring intervals, or lifestyle modifications recommended?",
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
                        # For single biomarker definitions, skip thinking tokens by default unless explicitly configured,
                        # avoiding 2-4 seconds of unnecessary reasoning latency per analyte.
                        test_thinking = os.environ.get("EXPLANATION_THINKING_TEST", "").lower() in ("1", "true", "yes")
                        thinking_config = None
                        if test_thinking and self.thinking_level and ("flash-lite" in cand_model.lower() or "gemini-3" in cand_model.lower() or "2.5" in cand_model.lower()):
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
