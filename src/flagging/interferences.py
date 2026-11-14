"""Medication & Supplement Pre-Analytical Interference Checker.

Identifies common pharmacological and nutritional substances that can falsely skew
or clinically influence laboratory biomarker assays.
Helps patients and physicians distinguish between genuine pathology and assay interference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.extraction.schema import FlagStatus, TestResult


@dataclass
class DrugLabInterference:
    analyte_name: str
    substance_name: str
    category: str  # "Supplement", "Prescription", "Dietary Factor"
    direction_of_skew: str  # "Falsely Elevates", "Falsely Lowers", "Clinically Elevates", "Clinically Depletes"
    clinical_mechanism_en: str
    clinical_mechanism_hi: str
    guidance_en: str
    guidance_hi: str


# Knowledge base of known pharmacological and supplement pre-analytical interactions
INTERFERENCE_RULES = [
    {
        "keywords": ["tsh", "thyroid stimulating hormone", "ft3", "ft4", "free t3", "free t4", "troponin"],
        "substance": "Biotin (Vitamin B7 / Hair & Nail Supplements)",
        "category": "Over-the-Counter Supplement",
        "direction": "Falsely Distorts (Immunoassay Interference)",
        "mechanism_en": "High-dose biotin (>5-10 mg/day) binds to streptavidin in laboratory immunoassays. It falsely suppresses TSH (mimicking hyperthyroidism), falsely elevates Free T3/T4, and can falsely suppress cardiac troponin.",
        "mechanism_hi": "बायोटिन (विटामिन B7) लैब टेस्ट की रासायनिक प्रणाली में बाधा डालता है। यह TSH को झूठा कम और थायराइड हार्मोन (T3/T4) को झूठा बढ़ा हुआ दिखा सकता है।",
        "guidance_en": "Endocrine Society guidelines advise stopping high-dose biotin supplements 48 to 72 hours before elective thyroid and cardiac blood draws.",
        "guidance_hi": "थायराइड या दिल की जांच कराने से 2 से 3 दिन पहले बायोटिन युक्त सप्लीमेंट का सेवन रोकने की सलाह दी जाती है।",
    },
    {
        "keywords": ["sgpt", "alt", "alanine", "sgot", "ast", "aspartate"],
        "substance": "Statins (Atorvastatin, Rosuvastatin, Simvastatin)",
        "category": "Prescription Medication",
        "direction": "Clinically Elevates (Mild Hepatic Transaminitis)",
        "mechanism_en": "HMG-CoA reductase inhibitors (statins) can cause benign, self-limiting elevations in liver transaminases (AST/ALT) in 1-3% of patients, usually reflecting hepatic metabolic adaptation rather than irreversible toxic injury.",
        "mechanism_hi": "कोलेस्ट्रॉल कम करने वाली स्टैटिन दवाएं कुछ मरीजों में लिवर एंजाइम (AST/ALT) में मामूली और हानिरहित वृद्धि कर सकती हैं।",
        "guidance_en": "Routine discontinuation is rarely indicated if transaminases remain under 3x the upper limit of normal; inform your prescribing physician.",
        "guidance_hi": "यदि स्तर 3 गुना से कम बढ़ा है तो घबराएं नहीं, लेकिन अपने डॉक्टर को वर्तमान दवाओं की जानकारी अवश्य दें।",
    },
    {
        "keywords": ["potassium"],
        "substance": "ACE Inhibitors / ARBs (Lisinopril, Enalapril, Telmisartan, Losartan)",
        "category": "Prescription Medication",
        "direction": "Clinically Elevates (Hyperkalemia Tendency)",
        "mechanism_en": "These antihypertensive medications decrease aldosterone synthesis in the adrenal cortex, reducing renal potassium excretion and occasionally causing potassium accumulation.",
        "mechanism_hi": "ब्लड प्रेशर की दवाएं (ACEI/ARBs) गुर्दे द्वारा पोटेशियम की निकासी को धीमा कर सकती हैं, जिससे खून में पोटेशियम बढ़ सकता है।",
        "guidance_en": "Avoid potassium-based salt substitutes (potassium chloride) and discuss current blood pressure drug dosages with your doctor.",
        "guidance_hi": "पोटेशियम युक्त 'लो-सोडियम सॉल्ट' से बचें और डॉक्टर से अपनी बीपी दवाओं की जांच कराएं।",
    },
    {
        "keywords": ["creatinine"],
        "substance": "Creatine Monohydrate & Heavy Protein Intake",
        "category": "Fitness Supplement & Diet",
        "direction": "Falsely/Clinically Elevates Serum Creatinine",
        "mechanism_en": "Creatine supplement ingestion and vigorous resistance training increase muscle mass turnover and conversion into creatinine, elevating serum levels without genuine loss of kidney glomerular filtration rate.",
        "mechanism_hi": "जिम वर्कआउट या 'क्रिएटिन' सप्लीमेंट लेने से खून में क्रिएटिनिन का स्तर बढ़ सकता है, जो गुर्दे की वास्तविक खराबी नहीं बल्कि सप्लीमेंट का असर होता है।",
        "guidance_en": "A cystatin-C test or fasting 48-hour cessation of creatine supplements provides a more accurate assessment of actual kidney function.",
        "guidance_hi": "सही स्थिति जानने के लिए सिस्टैटिन-सी (Cystatin-C) जांच करवाएं या 48 घंटे सप्लीमेंट रोककर दोबारा टेस्ट कराएं।",
    },
    {
        "keywords": ["glucose", "fasting blood sugar", "wbc", "total leukocyte count"],
        "substance": "Corticosteroids (Prednisone, Dexamethasone, Hydrocortisone)",
        "category": "Prescription Medication",
        "direction": "Clinically Elevates Glucose & WBCs",
        "mechanism_en": "Glucocorticoids increase hepatic gluconeogenesis, induce temporary peripheral insulin resistance, and cause demargination of intravascular neutrophils, elevating blood glucose and leukocyte counts.",
        "mechanism_hi": "स्टेरॉयड दवाओं के सेवन से रक्त शर्करा (शुगर) और सफेद रक्त कोशिकाओं (WBC) की संख्या में अस्थायी रूप से वृद्धि हो सकती है।",
        "guidance_en": "Always mention current or recent steroid use (inhalers, oral pills, or injections) when interpreting elevated sugars or blood counts.",
        "guidance_hi": "रिपोर्ट दिखाते समय डॉक्टर को अवश्य बताएं कि क्या आपने हाल ही में कोई स्टेरॉयड दवा ली है।",
    },
    {
        "keywords": ["uric acid"],
        "substance": "Thiazide & Loop Diuretics (Hydrochlorothiazide, Chlorthalidone, Furosemide)",
        "category": "Prescription Medication",
        "direction": "Clinically Elevates Serum Uric Acid",
        "mechanism_en": "Diuretic-induced volume contraction enhances proximal tubular reabsorption of urate, frequently producing asymptomatic hyperuricemia or precipitating acute gout flares.",
        "mechanism_hi": "पेशाब बढ़ाने वाली 'डाइयुरेटिक' दवाएं गुर्दे द्वारा यूरिक एसिड की निकासी कम कर देती हैं, जिससे खून में यूरिक एसिड बढ़ सकता है।",
        "guidance_en": "Ensure adequate daily water hydration; notify your doctor if you experience acute joint swelling (especially the big toe).",
        "guidance_hi": "पर्याप्त मात्रा में पानी पिएं और जोड़ों में दर्द या सूजन होने पर तुरंत चिकित्सक को सूचित करें।",
    },
]


class DrugInterferenceEngine:
    """Engine identifying potential medication and supplement interference with lab results."""

    def evaluate(self, tests: List[TestResult]) -> List[DrugLabInterference]:
        """Scan out-of-range or flagged tests and return potential pre-analytical interferences."""
        interferences: List[DrugLabInterference] = []
        seen_pairs = set()

        # Identify tests that are abnormal or flagged
        flagged_tests = [
            t for t in tests
            if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN) or t.value is not None
        ]

        for test in flagged_tests:
            tn_lower = test.test_name.strip().lower()

            for rule in INTERFERENCE_RULES:
                matches_analyte = any(kw in tn_lower for kw in rule["keywords"])
                if matches_analyte:
                    pair_key = (test.test_name, rule["substance"])
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        interferences.append(
                            DrugLabInterference(
                                analyte_name=test.test_name,
                                substance_name=rule["substance"],
                                category=rule["category"],
                                direction_of_skew=rule["direction"],
                                clinical_mechanism_en=rule["mechanism_en"],
                                clinical_mechanism_hi=rule["mechanism_hi"],
                                guidance_en=rule["guidance_en"],
                                guidance_hi=rule["guidance_hi"],
                            )
                        )

        return interferences
