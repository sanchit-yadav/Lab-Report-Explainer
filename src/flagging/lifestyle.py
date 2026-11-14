"""Evidence-Based Lifestyle & Nutrition Guidance Engine.

Generates deterministic, guideline-grounded dietary and lifestyle recommendations
(AHA, ADA, EASL, KDIGO) customized to a patient's abnormal biomarker panels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.extraction.schema import FlagStatus, TestResult


@dataclass
class LifestyleGuidance:
    panel_name: str
    target_analytes: List[str]
    nutrition_title_en: str
    nutrition_title_hi: str
    key_recommendations_en: List[str]
    key_recommendations_hi: List[str]
    foods_to_favor_en: List[str]
    foods_to_favor_hi: List[str]
    foods_to_limit_en: List[str]
    foods_to_limit_hi: List[str]
    clinical_evidence_source: str


LIFESTYLE_PROTOCOLS = [
    {
        "panel_name": "Cardiovascular & Lipid Health",
        "keywords": ["cholesterol", "triglyceride", "ldl", "vldl", "hdl"],
        "title_en": "AHA / ESC Mediterranean-Style Heart-Healthy Nutrition",
        "title_hi": "हृदय-सुरक्षा एवं लिपिड नियंत्रण पोषण योजना",
        "recommendations_en": [
            "Increase soluble viscous fiber to 10-25g daily (binds bile acids in the intestine, actively lowering LDL).",
            "Substitute saturated cooking fats (butter, palm oil) with monounsaturated extra-virgin olive oil or mustard oil.",
            "For elevated triglycerides: strictly minimize refined sugar and alcohol, and consume fatty fish (or flaxseed/walnuts) 2x weekly.",
            "Incorporate 150 minutes of moderate aerobic activity weekly (brisk walking, cycling) to elevate cardioprotective HDL.",
        ],
        "recommendations_hi": [
            "घुलनशील फाइबर (ओट्स, ईसबगोल, दालें) बढ़ाएं — यह आंतों में अतिरिक्त कोलेस्ट्रॉल को बांधकर बाहर निकालता है।",
            "घी, मक्खन और पाम तेल की जगह कम मात्रा में सरसों या जैतून के तेल का उपयोग करें।",
            "ट्राइग्लिसराइड्स कम करने के लिए मीठी चीजें और शराब पूरी तरह बंद करें।",
            "सप्ताह में कम से कम 150 मिनट तेज चलना या व्यायाम करें, जिससे सुरक्षात्मक HDL कोलेस्ट्रॉल बढ़ता है।",
        ],
        "favor_en": ["Oats & Barley", "Psyllium Husk", "Almonds & Walnuts", "Lentils & Chickpeas", "Extra Virgin Olive Oil"],
        "favor_hi": ["जई (ओट्स)", "ईसबगोल", "बादाम और अखरोट", "दालें और छोले", "जैतून व सरसों का तेल"],
        "limit_en": ["Deep-fried savories (Samosa, Pakora)", "Commercial baked goods", "Processed meats", "Sugary sodas"],
        "limit_hi": ["तले हुए पकवान व समोसे", "बेकरी बिस्कुट व पेस्ट्री", "प्रोसेस्ड मीट", "मीठे कोल्ड ड्रिंक्स"],
        "evidence": "American Heart Association (AHA) & European Society of Cardiology (ESC) Dyslipidemia Guidelines",
    },
    {
        "panel_name": "Glycemic & Metabolic Regulation",
        "keywords": ["glucose", "fasting blood sugar", "hba1c", "glycated hemoglobin"],
        "title_en": "ADA Glycemic Control & Insulin Sensitivity Protocol",
        "title_hi": "मधुमेह रोकथाम एवं शर्करा नियंत्रण आहार योजना",
        "recommendations_en": [
            "Adopt the 'Plate Method': 50% non-starchy vegetables, 25% lean protein, and 25% whole grains/complex carbs.",
            "Practice meal sequencing: consume fiber and protein before carbohydrates to significantly blunt post-meal blood sugar spikes.",
            "Take a 10-15 minute light brisk walk within 30 minutes after major meals to stimulate insulin-independent muscle glucose uptake.",
            "Avoid rapid-acting liquid calories (juices, sweet teas) which trigger sharp glycemic spikes.",
        ],
        "recommendations_hi": [
            "थाली में 50% हरी सब्जियां, 25% प्रोटीन (दाल, पनीर, अंडा) और 25% साबुत अनाज रखें।",
            "भोजन की शुरुआत सलाद और दाल से करें, रोटी/चावल बाद में खाएं — इससे शुगर तेजी से नहीं बढ़ती।",
            "भोजन के बाद 10-15 मिनट टहलें, जिससे मांसपेशियां बिना इंसुलिन के भी अतिरिक्त ग्लूकोज सोख लेती हैं।",
            "फलों के डिब्बाबंद जूस और मीठी चाय से पूरी तरह बचें।",
        ],
        "favor_en": ["Fenugreek (Methi) seeds", "Bitter Gourd (Karela)", "Chia / Flax seeds", "Brown rice / Quinoa", "Green leafy vegetables"],
        "favor_hi": ["मेथी दाना", "करेला", "अलसी के बीज", "ब्राउन राइस / बाजरा", "हरी पत्तेदार सब्जियां"],
        "limit_en": ["Refined white flour (Maida)", "White bread & refined pasta", "Fruit juices", "Sweets & Jaggery excess"],
        "limit_hi": ["मैदा और सफेद ब्रेड", "सफेद चीनी और मिठाई", "फलों के जूस", "सफेद चावल की अधिक मात्रा"],
        "evidence": "American Diabetes Association (ADA) Standards of Care in Diabetes",
    },
    {
        "panel_name": "Hepatic Metabolic Health",
        "keywords": ["sgot", "sgpt", "alt", "ast", "bilirubin", "gamma gt", "ggt"],
        "title_en": "EASL Hepatic Steatosis & Cellular Recovery Protocol",
        "title_hi": "लिवर स्वास्थ्य एवं फैटी लिवर सुधार योजना",
        "recommendations_en": [
            "A 7-10% gradual reduction in overall body weight reverses hepatic fat accumulation and normalizes transaminases.",
            "Complete alcohol avoidance during active transaminase elevation to permit liver hepatocyte regeneration.",
            "Strictly eliminate high-fructose corn syrup and sweetened carbonated beverages which accelerate liver lipogenesis.",
            "Moderate filtered black coffee intake (2-3 cups daily, if tolerated) has strong observational data reducing hepatic fibrosis.",
        ],
        "recommendations_hi": [
            "वजन में 7-10% की धीरे-धीरे कमी लिवर में जमी वसा को साफ करने में सबसे ज्यादा कारगर है।",
            "एंजाइम बढ़े होने के दौरान शराब का सेवन पूरी तरह से बंद रखें।",
            "अतिरिक्त फ्रुक्टोज और कोल्ड ड्रिंक्स से बचें जो सीधे लिवर में फैट बनाते हैं।",
            "बिना चीनी की हल्की ब्लैक कॉफी लिवर की कोशिकाओं की रक्षा करने में मददगार मानी जाती है।",
        ],
        "favor_en": ["Black coffee (sugar-free)", "Turmeric (Curcumin)", "Garlic", "Cruciferous veggies (Broccoli, Cauliflower)", "Green tea"],
        "favor_hi": ["बिना चीनी की ब्लैक कॉफी", "हल्दी", "लहसुन", "ब्रोकोली और गोभी", "ग्रीन टी"],
        "limit_en": ["Alcoholic beverages", "High-fructose corn syrup", "Heavy animal fats", "Ultra-processed packaged snacks"],
        "limit_hi": ["शराब और बीयर", "पैकेज्ड मीठे स्नैक्स", "डालडा व ट्रांस फैट", "अत्यधिक मसालेदार व बासी खाना"],
        "evidence": "European Association for the Study of the Liver (EASL) MASLD/NAFLD Guidelines",
    },
    {
        "panel_name": "Hematologic & Anemia Support",
        "keywords": ["hemoglobin", "mcv", "mch", "rbc count", "iron", "ferritin"],
        "title_en": "WHO Dietary Iron Bioavailability & Absorption Protocol",
        "title_hi": "रक्त निर्माण एवं हीमोग्लोबिन वृद्धि आहार योजना",
        "recommendations_en": [
            "Pair non-heme iron foods (lentils, spinach, jaggery) with Vitamin C rich sources (lemon, amla, bell peppers) to boost absorption by up to 300%.",
            "Strictly avoid drinking tea, green tea, or coffee within 1-2 hours before or after meals (tannins and polyphenols inhibit iron uptake by up to 60%).",
            "Do not consume high-calcium dairy supplements simultaneously with iron-rich foods, as calcium competes for intestinal iron transport.",
            "Cook in traditional cast-iron cookware to naturally enrich dietary iron content.",
        ],
        "recommendations_hi": [
            "आयरन युक्त भोजन (दाल, पालक, गुड़) के साथ नींबू या आंवला जरूर लें — विटामिन C आयरन का अवशोषण 3 गुना बढ़ा देता है।",
            "खाने के 1 घंटा पहले और 1 घंटा बाद तक चाय या कॉफी बिल्कुल न पिएं (यह आयरन को सोखने से रोकती है)।",
            "दूध या कैल्शियम की गोली को आयरन युक्त भोजन के तुरंत साथ न लें।",
            "लोहे की कड़ाही में खाना पकाने से भोजन में प्राकृतिक आयरन की मात्रा बढ़ती है।",
        ],
        "favor_en": ["Spinach & Moringa (Sahjan)", "Lentils & Kidney Beans", "Pomegranate & Beetroot", "Indian Gooseberry (Amla)", "Dates & Raisins"],
        "favor_hi": ["पालक और सहजन", "दालें और राजमा", "अनार और चुकंदर", "आंवला", "खजूर और किशमिश"],
        "limit_en": ["Tea/Coffee close to meals", "Excess calcium antacids with food", "Refined cereal empty calories"],
        "limit_hi": ["खाने के साथ चाय/कॉफी", "खाने के तुरंत बाद कैल्शियम सप्लीमेंट", "खाली पेट अधिक कैफीन"],
        "evidence": "World Health Organization (WHO) Nutritional Anaemias Guidelines",
    },
]


class LifestyleEngine:
    """Engine mapping abnormal lab test panels to guideline-grounded lifestyle interventions."""

    def evaluate(self, tests: List[TestResult]) -> List[LifestyleGuidance]:
        """Examine out-of-range analytes and return targeted nutrition and lifestyle protocols."""
        guidance_list: List[LifestyleGuidance] = []

        flagged_tests = [
            t for t in tests
            if t.flag not in (FlagStatus.NORMAL, FlagStatus.UNKNOWN)
        ]

        for proto in LIFESTYLE_PROTOCOLS:
            matched_analytes = []
            for test in flagged_tests:
                tn_lower = test.test_name.strip().lower()
                if any(kw in tn_lower for kw in proto["keywords"]):
                    matched_analytes.append(test.test_name)

            if matched_analytes:
                guidance_list.append(
                    LifestyleGuidance(
                        panel_name=proto["panel_name"],
                        target_analytes=list(dict.fromkeys(matched_analytes)),
                        nutrition_title_en=proto["title_en"],
                        nutrition_title_hi=proto["title_hi"],
                        key_recommendations_en=proto["recommendations_en"],
                        key_recommendations_hi=proto["recommendations_hi"],
                        foods_to_favor_en=proto["favor_en"],
                        foods_to_favor_hi=proto["favor_hi"],
                        foods_to_limit_en=proto["limit_en"],
                        foods_to_limit_hi=proto["limit_hi"],
                        clinical_evidence_source=proto["evidence"],
                    )
                )

        return guidance_list
