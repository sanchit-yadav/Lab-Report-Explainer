"""Critical Panic Value Emergency Protocol.

Hospital laboratories (CAP, CLIA, ISO 15189) enforce immediate clinician notification
when laboratory measurements cross life-threatening physiological boundaries.
This module evaluates test results against verified medical panic thresholds deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from src.extraction.schema import TestResult


class PanicSeverity(str, Enum):
    IMMEDIATE_EMERGENCY = "IMMEDIATE_EMERGENCY"
    URGENT_ATTENTION = "URGENT_ATTENTION"


@dataclass
class PanicAlert:
    test_name: str
    observed_value: float
    unit: str
    severity: PanicSeverity
    clinical_risk_en: str
    clinical_risk_hi: str
    action_protocol_en: str
    action_protocol_hi: str
    doctor_questions: List[str]


# Verified clinical emergency critical boundaries
PANIC_THRESHOLDS = {
    "potassium": {
        "critical_low": 2.8,
        "critical_high": 6.2,
        "unit": "mEq/L",
        "low_risk_en": "Severe hypokalemia can cause life-threatening cardiac arrhythmias, muscle paralysis, and respiratory failure.",
        "low_risk_hi": "पोटेशियम का अत्यधिक कम स्तर हृदय गति में जानलेवा अनियमितता (एरिदमिया) और मांसपेशियों में कमजोरी पैदा कर सकता है।",
        "high_risk_en": "Severe hyperkalemia can trigger sudden fatal ventricular arrhythmias, heart block, or cardiac arrest.",
        "high_risk_hi": "पोटेशियम का अत्यधिक उच्च स्तर अचानक कार्डियक अरेस्ट और गंभीर हृदय विकार का कारण बन सकता है।",
        "action_en": "Seek immediate emergency medical evaluation. Contact your doctor or visit the nearest emergency department without delay.",
        "action_hi": "बिना देरी किए तुरंत आपातकालीन चिकित्सा सहायता (Emergency Room) प्राप्त करें या अपने डॉक्टर से संपर्क करें।",
        "questions": [
            "Does this potassium level require immediate inpatient stabilization or an urgent repeat test?",
            "Should an immediate 12-lead ECG (electrocardiogram) be performed to assess cardiac rhythm?",
        ],
    },
    "sodium": {
        "critical_low": 120.0,
        "critical_high": 160.0,
        "unit": "mEq/L",
        "low_risk_en": "Severe hyponatremia can lead to cerebral edema, seizures, confusion, and coma.",
        "low_risk_hi": "सोडियम का बहुत कम स्तर मस्तिष्क में सूजन, दौरे (seizures) और बेहोशी का कारण बन सकता है।",
        "high_risk_en": "Severe hypernatremia causes profound cellular dehydration, neurological damage, and hemodynamic instability.",
        "high_risk_hi": "सोडियम का बहुत अधिक स्तर शरीर में अत्यधिक पानी की कमी और तंत्रिका तंत्र को गंभीर नुकसान पहुंचा सकता है।",
        "action_en": "Contact your physician or proceed to an emergency department for controlled electrolyte management.",
        "action_hi": "तत्काल डॉक्टर से परामर्श करें या अस्पताल के आपातकालीन विभाग में जाएं।",
        "questions": [
            "What is the underlying cause of this acute electrolyte imbalance?",
            "What fluid rate or protocol should be used to safely normalize this level?",
        ],
    },
    "hemoglobin": {
        "critical_low": 7.0,
        "critical_high": 20.0,
        "unit": "g/dL",
        "low_risk_en": "Critical anemia with hemoglobin below 7.0 g/dL severely impairs oxygen delivery, risking myocardial ischemia and cardiac collapse.",
        "low_risk_hi": "हीमोग्लोबिन 7.0 g/dL से कम होना गंभीर एनीमिया है, जिससे अंगों में ऑक्सीजन की भारी कमी और दिल पर अत्यधिक दबाव पड़ता है।",
        "high_risk_en": "Marked polycythemia (Hb > 20 g/dL) drastically increases blood viscosity, risking stroke and thromboembolism.",
        "high_risk_hi": "हीमोग्लोबिन अत्यधिक उच्च होने से रक्त बहुत गाढ़ा हो जाता है, जिससे स्ट्रोक या खून के थक्के जमने का खतरा बढ़ जाता है।",
        "action_en": "Requires prompt clinical review. Inpatient transfusion or specialized hematology assessment may be indicated.",
        "action_hi": "तुरंत रक्त रोग विशेषज्ञ (हेमेटोलॉजिस्ट) या आपातकालीन चिकित्सक से संपर्क करें।",
        "questions": [
            "Is an urgent blood transfusion or iron infusion medically required?",
            "What diagnostic tests are recommended to determine the source of blood loss or production failure?",
        ],
    },
    "platelet count": {
        "critical_low": 20000.0,
        "critical_high": 1000000.0,
        "unit": "/cumm",
        "low_risk_en": "Severe thrombocytopenia (< 20,000/µL) poses an imminent danger of spontaneous mucosal, gastrointestinal, or intracranial hemorrhage.",
        "low_risk_hi": "प्लेटलेट्स 20,000 से कम होना स्वतः आंतरिक रक्तस्राव (ब्लीडिंग) का जानलेवा जोखिम पैदा करता है।",
        "high_risk_en": "Extreme thrombocytosis (> 1,000,000/µL) dramatically heightens the risk of both thrombosis and paradoxical bleeding.",
        "high_risk_hi": "प्लेटलेट्स 10 लाख से अधिक होने पर नसों में खून के थक्के जमने का भारी खतरा होता है।",
        "action_en": "Avoid any strenuous activity, contact sports, or aspirin/NSAIDs. Seek immediate emergency evaluation.",
        "action_hi": "कोई भी भारी काम न करें और खून पतला करने वाली दवाएं तुरंत रोकें। बिना देरी किए डॉक्टर को दिखाएं।",
        "questions": [
            "Is platelet transfusion or urgent bone marrow evaluation necessary?",
            "What activity precautions should be instituted immediately?",
        ],
    },
    "fasting blood sugar": {
        "critical_low": 50.0,
        "critical_high": 400.0,
        "unit": "mg/dL",
        "low_risk_en": "Severe hypoglycemia (< 50 mg/dL) can rapidly cause neuroglycopenia, loss of consciousness, and seizures.",
        "low_risk_hi": "ग्लूकोज 50 से कम होना गंभीर हाइपोग्लाइसीमिया है, जिससे चक्कर, बेहोशी और मस्तिष्क को क्षति हो सकती है।",
        "high_risk_en": "Severe hyperglycemia (> 400 mg/dL) risks Diabetic Ketoacidosis (DKA) or Hyperosmolar Hyperglycemic State (HHS).",
        "high_risk_hi": "ग्लूकोज 400 से अधिक होना डायबिटिक कीटोएसिडोसिस (DKA) जैसी जानलेवा जटिलता का जोखिम पैदा करता है।",
        "action_en": "For low sugar: consume fast-acting carbohydrates immediately. For extreme highs: seek prompt physician guidance.",
        "action_hi": "लो शुगर होने पर तुरंत मीठा खाएं/पिएं। अत्यधिक शुगर होने पर तत्काल डॉक्टर से संपर्क करें।",
        "questions": [
            "Are urine ketones present, and is insulin regimen adjustment urgently needed?",
            "What target blood glucose range should be maintained over the next 24 hours?",
        ],
    },
    "glucose - fasting": {
        "alias_of": "fasting blood sugar",
    },
    "calcium": {
        "critical_low": 6.5,
        "critical_high": 13.0,
        "unit": "mg/dL",
        "low_risk_en": "Severe hypocalcemia can trigger acute neuromuscular tetany, laryngospasm, and cardiac prolongation.",
        "low_risk_hi": "कैल्शियम का बहुत कम स्तर मांसपेशियों में खिंचाव (टेटनी) और सांस नली में ऐंठन ला सकता है।",
        "high_risk_en": "Severe hypercalcemia risks hypercalcemic crisis, altered mental status, and acute renal failure.",
        "high_risk_hi": "कैल्शियम बहुत अधिक होना हाइपरकैल्सीमिक क्राइसिस, भ्रम और गुर्दे की विफलता का कारण बन सकता है।",
        "action_en": "Requires urgent medical consultation for intravenous electrolyte support or calcitonin therapy.",
        "action_hi": "तुरंत अस्पताल जाकर डॉक्टर से परामर्श लें।",
        "questions": [
            "What is the corrected calcium level based on serum albumin?",
            "Should parathyroid hormone (PTH) and vitamin D levels be measured urgently?",
        ],
    },
    "total bilirubin": {
        "critical_low": None,
        "critical_high": 15.0,
        "unit": "mg/dL",
        "low_risk_en": "",
        "low_risk_hi": "",
        "high_risk_en": "Marked hyperbilirubinemia (> 15 mg/dL) suggests severe acute liver failure, high-grade biliary obstruction, or active hemolysis.",
        "high_risk_hi": "बिलीरुबिन 15 से अधिक होना लिवर की गंभीर विफलता या पित्त नली में बड़ी रुकावट का संकेत है।",
        "action_en": "Requires prompt hepatology or gastroenterology evaluation and abdominal ultrasound imaging.",
        "action_hi": "तुरंत लिवर विशेषज्ञ से मिलें और पेट का अल्ट्रासाउंड करवाएं।",
        "questions": [
            "Is there evidence of biliary tract obstruction or acute viral/toxic hepatitis?",
            "What are the direct vs indirect bilirubin proportions?",
        ],
    },
    "wbc count": {
        "critical_low": 1500.0,
        "critical_high": 30000.0,
        "unit": "/cumm",
        "low_risk_en": "Severe leukopenia / neutropenia leaves the body defenseless against overwhelming sepsis and opportunistic infections.",
        "low_risk_hi": "सफेद रक्त कोशिकाओं का 1,500 से कम होना शरीर को गंभीर और जानलेवा संक्रमणों के प्रति असुरक्षित बना देता है।",
        "high_risk_en": "Marked leukocytosis (> 30,000/µL) can indicate fulminant bacterial sepsis, leukemoid reaction, or acute hematologic malignancy.",
        "high_risk_hi": "WBC का 30,000 से ऊपर होना गंभीर संक्रमण, सेप्सिस या रक्त संबंधी बीमारी का संकेत हो सकता है।",
        "action_en": "Monitor for fever or chills immediately. Seek emergency clinical review.",
        "action_hi": "बुखार या ठंड लगने पर तुरंत अस्पताल पहुंचे। डॉक्टर से तत्काल सलाह लें।",
        "questions": [
            "What is the Absolute Neutrophil Count (ANC)?",
            "Are broad-spectrum antibiotics or hematology consultation indicated?",
        ],
    },
}


def _match_panic_key(test_name: str) -> Optional[str]:
    """Match analyte name to panic threshold rules."""
    tn = test_name.strip().lower()
    for key, spec in PANIC_THRESHOLDS.items():
        if "alias_of" in spec:
            canonical = spec["alias_of"]
            if key in tn or tn == key:
                return canonical
        elif key in tn or tn == key:
            return key
    return None


class PanicValueEngine:
    """Deterministic evaluation engine identifying critical medical panic values."""

    def evaluate(self, tests: List[TestResult]) -> List[PanicAlert]:
        """Scan a list of test results and return all active panic alerts."""
        alerts: List[PanicAlert] = []

        for test in tests:
            if test.value is None:
                continue

            matched_key = _match_panic_key(test.test_name)
            if not matched_key:
                continue

            spec = PANIC_THRESHOLDS.get(matched_key)
            if not spec or "alias_of" in spec:
                continue

            c_low = spec.get("critical_low")
            c_high = spec.get("critical_high")
            val = float(test.value)

            # Check critical low
            if c_low is not None and val < c_low:
                alerts.append(
                    PanicAlert(
                        test_name=test.test_name,
                        observed_value=val,
                        unit=test.unit or spec.get("unit", ""),
                        severity=PanicSeverity.IMMEDIATE_EMERGENCY,
                        clinical_risk_en=spec["low_risk_en"],
                        clinical_risk_hi=spec["low_risk_hi"],
                        action_protocol_en=spec["action_en"],
                        action_protocol_hi=spec["action_hi"],
                        doctor_questions=spec.get("questions", []),
                    )
                )

            # Check critical high
            elif c_high is not None and val > c_high:
                alerts.append(
                    PanicAlert(
                        test_name=test.test_name,
                        observed_value=val,
                        unit=test.unit or spec.get("unit", ""),
                        severity=PanicSeverity.IMMEDIATE_EMERGENCY,
                        clinical_risk_en=spec["high_risk_en"],
                        clinical_risk_hi=spec["high_risk_hi"],
                        action_protocol_en=spec["action_en"],
                        action_protocol_hi=spec["action_hi"],
                        doctor_questions=spec.get("questions", []),
                    )
                )

        return alerts
