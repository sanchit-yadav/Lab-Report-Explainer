"""Deterministic Cross-Analyte Correlation Engine.

Evaluates recognized multi-analyte clinical ratios and physiological patterns
in pure Python (zero LLM hallucination risk) based on established laboratory medicine
guidelines (AACC, ADA, KDIGO, EASL).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.extraction.schema import FlagStatus, TestResult


class CorrelationSeverity(str, Enum):
    NORMAL = "normal"
    BORDERLINE = "borderline"
    ELEVATED = "elevated"
    HIGH = "high"


class ClinicalCorrelation(BaseModel):
    """Structured representation of a multi-analyte clinical pattern or ratio."""
    panel_name: str = Field(description="Clinical domain (e.g. Lipid Profile, Liver Function, Kidney Function, Anemia)")
    title: str = Field(description="Clinical title of the evaluated pattern")
    value: Optional[float] = Field(default=None, description="Calculated numeric ratio value if applicable")
    unit: str = Field(default="", description="Ratio notation or unit")
    optimal_range: str = Field(default="", description="Target clinical benchmark")
    severity: CorrelationSeverity = Field(default=CorrelationSeverity.NORMAL, description="Risk/severity assessment")
    finding_en: str = Field(description="Educational explanation in English")
    finding_hi: str = Field(description="Educational explanation in Hindi")
    doctor_questions: List[str] = Field(default_factory=list, description="Targeted clinical consultation questions")


# Canonical alias mappings for common laboratory analytes
CANONICAL_ALIASES: Dict[str, List[str]] = {
    "total_cholesterol": [
        "total cholesterol", "cholesterol - total", "cholesterol, total", "cholesterol total", "cholesterol"
    ],
    "hdl": [
        "hdl", "hdl cholesterol", "hdl - cholesterol", "high density lipoprotein", "cholesterol - hdl"
    ],
    "triglycerides": [
        "triglycerides", "triglyceride", "tg", "serum triglycerides", "triglycerides - serum"
    ],
    "ldl": [
        "ldl", "ldl cholesterol", "ldl - cholesterol", "low density lipoprotein", "cholesterol - ldl"
    ],
    "ast": [
        "ast", "sgot", "aspartate aminotransferase", "sgot / ast", "aspartate transaminase", "sgot(ast)"
    ],
    "alt": [
        "alt", "sgpt", "alanine aminotransferase", "sgpt / alt", "alanine transaminase", "sgpt(alt)"
    ],
    "bun": [
        "bun", "blood urea nitrogen", "urea nitrogen"
    ],
    "urea": [
        "urea", "serum urea", "blood urea", "urea - serum"
    ],
    "creatinine": [
        "creatinine", "serum creatinine", "s. creatinine", "creatinine - serum"
    ],
    "hemoglobin": [
        "hemoglobin", "hb", "hgb", "haemoglobin"
    ],
    "mcv": [
        "mcv", "mean corpuscular volume"
    ],
    "ferritin": [
        "ferritin", "serum ferritin", "s. ferritin"
    ],
    "fasting_glucose": [
        "fasting blood sugar", "glucose - fasting", "fasting glucose", "fbs", "blood glucose fasting", "glucose, fasting"
    ],
    "hba1c": [
        "hba1c", "glycated hemoglobin", "hemoglobin a1c", "glycosylated hemoglobin", "hba1c (glycated hemoglobin)"
    ],
    "wbc": [
        "wbc", "total wbc count", "leukocyte count", "white blood cells", "total leucocyte count (tlc)", "tlc"
    ],
    "platelets": [
        "platelet count", "platelets", "total platelet count", "plt"
    ],
}


def _match_analyte(tests: List[TestResult], canonical_key: str) -> Optional[TestResult]:
    """Match an extracted analyte against known clinical name variations."""
    aliases = CANONICAL_ALIASES.get(canonical_key, [])
    for test in tests:
        if not test.test_name or test.value is None:
            continue
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", test.test_name.lower()).strip()
        cleaned_compact = re.sub(r"\s+", " ", cleaned)
        for alias in aliases:
            # Exact or substring match
            if alias == cleaned_compact or alias in cleaned_compact:
                return test
    return None


class CorrelationEngine:
    """Calculates pure-Python clinical correlations across interrelated laboratory tests."""

    def evaluate(self, tests: List[TestResult]) -> List[ClinicalCorrelation]:
        """Run all deterministic multi-analyte rules over the provided test results."""
        correlations: List[ClinicalCorrelation] = []

        # 1. Total Cholesterol / HDL Ratio (Cardiovascular Risk Index)
        tc = _match_analyte(tests, "total_cholesterol")
        hdl = _match_analyte(tests, "hdl")
        if tc and hdl and tc.value and hdl.value and hdl.value > 0:
            ratio = round(tc.value / hdl.value, 2)
            if ratio < 3.5:
                sev = CorrelationSeverity.NORMAL
                f_en = f"Your Total Cholesterol to HDL ratio is {ratio}, which is in the optimal cardiovascular health range (< 3.5)."
                f_hi = f"आपका कुल कोलेस्ट्रॉल / एचडीएल अनुपात {ratio} है, जो हृदय स्वास्थ्य के लिए सर्वोत्तम मानक (< 3.5) के भीतर है।"
            elif ratio <= 5.0:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"Your Total Cholesterol to HDL ratio is {ratio}, representing moderate cardiovascular risk (ideal target is < 3.5)."
                f_hi = f"आपका कुल कोलेस्ट्रॉल / एचडीएल अनुपात {ratio} है, जो मध्यम हृदय संबंधी जोखिम दर्शाता है (लक्ष्य < 3.5 है)।"
            else:
                sev = CorrelationSeverity.ELEVATED
                f_en = f"Your Total Cholesterol to HDL ratio is elevated at {ratio} (benchmark > 5.0 indicates higher atherogenic cardiovascular risk)."
                f_hi = f"आपका कुल कोलेस्ट्रॉल / एचडीएल अनुपात {ratio} पर बढ़ा हुआ है (5.0 से अधिक अनुपात हृदय संबंधी जोखिम का संकेत देता है)।"

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Lipid & Cardiovascular Panel",
                    title="Total Cholesterol / HDL Ratio",
                    value=ratio,
                    unit="ratio",
                    optimal_range="< 3.5 (Optimal), 3.5 - 5.0 (Moderate)",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=[
                        f"How does my Total Cholesterol / HDL ratio of {ratio} influence my overall cardiovascular management plan?",
                        "Would dietary interventions or regular aerobic exercise be sufficient to optimize this ratio?",
                    ],
                )
            )

        # 2. Triglyceride / HDL Ratio (Insulin Resistance Marker)
        tg = _match_analyte(tests, "triglycerides")
        if tg and hdl and tg.value and hdl.value and hdl.value > 0:
            ratio = round(tg.value / hdl.value, 2)
            if ratio < 2.0:
                sev = CorrelationSeverity.NORMAL
                f_en = f"Your Triglyceride / HDL ratio is {ratio}, reflecting favorable metabolic balance and insulin sensitivity (< 2.0)."
                f_hi = f"आपका ट्राइग्लिसराइड / एचडीएल अनुपात {ratio} है, जो सामान्य चयापचय और स्वस्थ इंसुलिन संवेदनशीलता (< 2.0) दर्शाता है।"
            elif ratio <= 3.8:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"Your Triglyceride / HDL ratio is {ratio}, which is borderline (2.0 - 3.8). Suggests mild metabolic resistance."
                f_hi = f"आपका ट्राइग्लिसराइड / एचडीएल अनुपात {ratio} सीमा पर है (2.0 - 3.8), जो हल्के चयापचय तनाव का संकेत हो सकता है।"
            else:
                sev = CorrelationSeverity.ELEVATED
                f_en = f"Your Triglyceride / HDL ratio is elevated at {ratio} (> 3.8), which strongly correlates with metabolic syndrome and insulin resistance."
                f_hi = f"आपका ट्राइग्लिसराइड / एचडीएल अनुपात {ratio} पर बढ़ा हुआ है (> 3.8), जो इंसुलिन प्रतिरोध और मेटाबॉलिक सिंड्रोम से जुड़ा हो सकता है।"

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Lipid & Metabolic Panel",
                    title="Triglyceride / HDL Ratio (Metabolic Indicator)",
                    value=ratio,
                    unit="ratio",
                    optimal_range="< 2.0 (Optimal), 2.0 - 3.8 (Borderline)",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=[
                        f"Does my Triglyceride / HDL ratio of {ratio} suggest insulin resistance or pre-metabolic changes?",
                        "What specific carbohydrate and refined sugar reduction steps should I take?",
                    ],
                )
            )

        # 3. De Ritis Ratio (AST / ALT) - Hepatic Profile
        ast = _match_analyte(tests, "ast")
        alt = _match_analyte(tests, "alt")
        if ast and alt and ast.value and alt.value and alt.value > 0:
            ratio = round(ast.value / alt.value, 2)
            # Evaluate only if at least one enzyme is outside normal or borderline
            is_abnormal = ast.flag != FlagStatus.NORMAL or alt.flag != FlagStatus.NORMAL
            if is_abnormal:
                if ratio > 2.0:
                    sev = CorrelationSeverity.HIGH
                    f_en = f"Your De Ritis ratio (AST/ALT) is {ratio} (> 2.0) with elevated transaminases. This pattern is commonly reviewed for toxic, alcoholic, or advanced hepatic parenchymal changes."
                    f_hi = f"आपका डी रिटिस अनुपात (AST/ALT) {ratio} (> 2.0) है और लिवर एंजाइम बढ़े हुए हैं। यह पैटर्न लिवर की गहरी क्षति या विषाक्त प्रभाव के मूल्यांकन हेतु विचारणीय है।"
                elif ratio < 1.0:
                    sev = CorrelationSeverity.BORDERLINE
                    f_en = f"Your De Ritis ratio (AST/ALT) is {ratio} (< 1.0) with enzyme elevation, which frequently characterizes non-alcoholic fatty liver disease (NAFLD) or acute hepatocellular inflammation."
                    f_hi = f"आपका डी रिटिस अनुपात (AST/ALT) {ratio} (< 1.0) है और एंजाइम बढ़े हैं, जो आमतौर पर फैटी लिवर (NAFLD) या लिवर सूजन में देखा जाता है।"
                else:
                    sev = CorrelationSeverity.BORDERLINE
                    f_en = f"Your De Ritis ratio (AST/ALT) is {ratio} with elevated liver enzymes, warranting general clinical follow-up."
                    f_hi = f"आपका डी रिटिस अनुपात {ratio} है और लिवर एंजाइमों में असंतुलन है, जिसके लिए सामान्य चिकित्सकीय फॉलो-अप की आवश्यकता है।"
            else:
                sev = CorrelationSeverity.NORMAL
                f_en = f"Your AST/ALT ratio is {ratio} with both liver transaminases within normal reference limits."
                f_hi = f"आपका AST/ALT अनुपात {ratio} है और दोनों लिवर एंजाइम सामान्य संदर्भ सीमा के भीतर हैं।"

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Liver Function Panel",
                    title="De Ritis Ratio (AST / ALT)",
                    value=ratio,
                    unit="ratio",
                    optimal_range="0.8 - 1.2 (Normal context)",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=[
                        f"How does my AST/ALT ratio of {ratio} correlate with my overall liver health and ultrasound findings (if any)?",
                        "Are there any medications or supplements I take that could influence these transaminase numbers?",
                    ],
                )
            )

        # 4. BUN / Creatinine Ratio - Renal Hemodynamics
        bun = _match_analyte(tests, "bun")
        urea = _match_analyte(tests, "urea")
        creat = _match_analyte(tests, "creatinine")

        # Convert Urea to BUN if BUN is not explicitly present (BUN ≈ Urea / 2.14)
        bun_val: Optional[float] = None
        if bun and bun.value:
            bun_val = bun.value
        elif urea and urea.value:
            bun_val = round(urea.value / 2.14, 1)

        if bun_val and creat and creat.value and creat.value > 0:
            ratio = round(bun_val / creat.value, 1)
            if ratio < 10.0:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"Your BUN to Creatinine ratio is {ratio}:1 (< 10:1), which can occur with reduced protein intake, severe liver disease, or intrinsic renal tubular conditions."
                f_hi = f"आपका बीयूएन / क्रिएटिनिन अनुपात {ratio}:1 (< 10:1) है, जो कम प्रोटीन सेवन या आंतरिक किडनी कार्यप्रणाली में बदलाव का संकेत हो सकता है।"
            elif ratio <= 20.0:
                sev = CorrelationSeverity.NORMAL
                f_en = f"Your BUN to Creatinine ratio is {ratio}:1, well within the normal physiological range of 10:1 to 20:1."
                f_hi = f"आपका बीयूएन / क्रिएटिनिन अनुपात {ratio}:1 है, जो 10:1 से 20:1 की सामान्य स्वस्थ सीमा में है।"
            else:
                sev = CorrelationSeverity.ELEVATED
                f_en = f"Your BUN to Creatinine ratio is {ratio}:1 (> 20:1). This disproportionate elevation is most commonly caused by dehydration, reduced renal blood flow, or high dietary protein."
                f_hi = f"आपका बीयूएन / क्रिएटिनिन अनुपात {ratio}:1 (> 20:1) बढ़ा हुआ है। यह आमतौर पर निर्जलीकरण (डिहाइड्रेशन) या कम पानी पीने के कारण होता है।"

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Kidney Function Panel",
                    title="BUN / Serum Creatinine Ratio",
                    value=ratio,
                    unit=":1",
                    optimal_range="10.0 - 20.0 :1",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=[
                        f"Does my BUN/Creatinine ratio of {ratio}:1 indicate that I need to improve hydration, or are further renal tests needed?",
                        "Should I re-test my kidney panel in a fasting, well-hydrated state?",
                    ],
                )
            )

        # 5. Anemia Phenotyping (Hemoglobin + MCV + Ferritin)
        hb = _match_analyte(tests, "hemoglobin")
        mcv = _match_analyte(tests, "mcv")
        if hb and hb.value and hb.flag in (FlagStatus.LOW, FlagStatus.CRITICAL_LOW):
            if mcv and mcv.value:
                if mcv.value < 80.0:
                    sev = CorrelationSeverity.HIGH
                    f_en = f"Low Hemoglobin ({hb.value} {hb.unit}) combined with low MCV ({mcv.value} fL) indicates a Microcytic Anemia pattern. The most frequent causes are iron deficiency or thalassemia trait."
                    f_hi = f"कम हीमोग्लोबिन ({hb.value} {hb.unit}) और कम एमसीवी ({mcv.value} fL) माइक्रोसिटिक एनीमिया का संकेत देते हैं। इसका सबसे आम कारण शरीर में आयरन की कमी हो सकता है।"
                    doctor_q = [
                        "Should we run a complete iron profile (Serum Iron, Ferritin, TIBC) to confirm iron deficiency anemia?",
                        "What dietary changes or therapeutic iron plans are appropriate for my situation?",
                    ]
                elif mcv.value > 100.0:
                    sev = CorrelationSeverity.HIGH
                    f_en = f"Low Hemoglobin ({hb.value} {hb.unit}) combined with elevated MCV ({mcv.value} fL) indicates a Macrocytic Anemia pattern, commonly associated with Vitamin B12 or Folate deficiency."
                    f_hi = f"कम हीमोग्लोबिन ({hb.value} {hb.unit}) और बढ़ा हुआ एमसीवी ({mcv.value} fL) मैक्रोसिटिक एनीमिया का संकेत देते हैं, जो अक्सर विटामिन बी12 या फोलेट की कमी से होता है।"
                    doctor_q = [
                        "Should we check my Serum Vitamin B12 and Folate levels?",
                        "Could any existing medications be interfering with vitamin absorption?",
                    ]
                else:
                    sev = CorrelationSeverity.BORDERLINE
                    f_en = f"Low Hemoglobin ({hb.value} {hb.unit}) with normal MCV ({mcv.value} fL) indicates a Normocytic Anemia pattern (often seen in anemia of chronic inflammation, kidney disease, or early blood loss)."
                    f_hi = f"कम हीमोग्लोबिन ({hb.value} {hb.unit}) सामान्य एमसीवी ({mcv.value} fL) के साथ नॉर्मोसिटिक एनीमिया दर्शाता है, जो अक्सर किसी पुरानी सूजन या अन्य स्थिति से संबंधित होता है।"
                    doctor_q = [
                        "What underlying causes should we investigate for this normocytic hemoglobin reduction?",
                        "Is a reticulocyte count or peripheral smear examination recommended?",
                    ]
            else:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"Hemoglobin is low at {hb.value} {hb.unit}. MCV is not available on this panel to classify the cell size."
                f_hi = f"हीमोग्लोबिन {hb.value} {hb.unit} पर कम है। इस रिपोर्ट में एमसीवी उपलब्ध नहीं है।"
                doctor_q = ["Should a Complete Blood Count with RBC indices be ordered?"]

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Hematology Panel",
                    title="Anemia Morphology Pattern",
                    value=None,
                    unit="",
                    optimal_range="Hb Normal & MCV 80-100 fL",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=doctor_q,
                )
            )

        # 6. Glycemic Concordance (Fasting Glucose + HbA1c)
        glucose = _match_analyte(tests, "fasting_glucose")
        hba1c = _match_analyte(tests, "hba1c")
        if glucose and hba1c and glucose.value and hba1c.value:
            g_high = glucose.value >= 126.0 or glucose.flag in (FlagStatus.HIGH, FlagStatus.CRITICAL_HIGH)
            a_high = hba1c.value >= 6.5 or hba1c.flag in (FlagStatus.HIGH, FlagStatus.CRITICAL_HIGH)

            if g_high and a_high:
                sev = CorrelationSeverity.HIGH
                f_en = f"Both Fasting Glucose ({glucose.value} mg/dL) and HbA1c ({hba1c.value}%) are concordantly elevated, demonstrating sustained chronic hyperglycemia across the 3-month window."
                f_hi = f"फास्टिंग ग्लूकोज ({glucose.value} mg/dL) और एचबीए1सी ({hba1c.value}%) दोनों बढ़े हुए हैं, जो पिछले 3 महीनों में लगातार बढ़े हुए ब्लड शुगर को दर्शाते हैं।"
                doctor_q = [
                    "What formal metabolic management and lifestyle changes do you advise based on both elevated markers?",
                    "Should we consult an endocrinologist for a comprehensive diabetes management protocol?",
                ]
            elif g_high and not a_high:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"Fasting Glucose is elevated ({glucose.value} mg/dL) but 3-month HbA1c remains normal ({hba1c.value}%). This acute discrepancy can reflect acute physical/emotional stress, recent carbohydrate intake, or early prediabetes."
                f_hi = f"फास्टिंग ग्लूकोज ({glucose.value} mg/dL) बढ़ा हुआ है लेकिन 3 महीने का एचबीए1सी ({hba1c.value}%) सामान्य है। यह तात्कालिक तनाव या हालिया खानपान का प्रभाव हो सकता है।"
                doctor_q = [
                    "Could this elevated fasting glucose be a transient acute fluctuation, and should it be repeated?",
                    "Would a Post-Prandial or Oral Glucose Tolerance Test be helpful?",
                ]
            elif not g_high and a_high:
                sev = CorrelationSeverity.BORDERLINE
                f_en = f"HbA1c is elevated ({hba1c.value}%) while Fasting Glucose is within normal limits ({glucose.value} mg/dL). This pattern points to postprandial (after-meal) glycemic spikes despite controlled overnight fasting."
                f_hi = f"एचबीए1सी ({hba1c.value}%) बढ़ा हुआ है जबकि फास्टिंग ग्लूकोज सामान्य है। यह भोजन के बाद शुगर में आने वाले उतार-चढ़ाव का संकेत देता है।"
                doctor_q = [
                    "Should we monitor post-meal (postprandial) glucose levels to catch after-meal spikes?",
                    "How can I adjust meal composition and carbohydrate timing to lower HbA1c?",
                ]
            else:
                sev = CorrelationSeverity.NORMAL
                f_en = f"Both Fasting Glucose ({glucose.value} mg/dL) and HbA1c ({hba1c.value}%) are concordant and within desirable clinical reference limits."
                f_hi = f"फास्टिंग ग्लूकोज ({glucose.value} mg/dL) और एचबीए1सी ({hba1c.value}%) दोनों सामान्य और संतुलित सीमा के भीतर हैं।"
                doctor_q = ["How often should routine glycemic screening be repeated for proactive maintenance?"]

            correlations.append(
                ClinicalCorrelation(
                    panel_name="Glycemic & Diabetes Panel",
                    title="Glycemic Concordance (Glucose vs HbA1c)",
                    value=None,
                    unit="",
                    optimal_range="Fasting < 100 mg/dL & HbA1c < 5.7%",
                    severity=sev,
                    finding_en=f_en,
                    finding_hi=f_hi,
                    doctor_questions=doctor_q,
                )
            )

        return correlations
