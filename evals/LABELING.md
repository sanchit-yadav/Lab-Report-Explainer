# Clinical Lab Report Evaluation & Ground-Truth Labeling Guide

**Target Application:** AI Clinical Lab Report Explainer  
**Standard Version:** 2026.1  
**Scope:** Diagnostic Laboratory Hematology, Lipid, Metabolic, Renal, and Hepatic Panels  

---

## 1. Overview & Objective

This labeling guide defines the clinical and engineering ground-truth annotation standards for the 60+ golden benchmark cases in `/evals/golden/`.

Every case consists of:
1. **Source Document Artifact:** A PDF or high-resolution PNG image representing a diagnostic report.
2. **Companion Ground-Truth JSON (`<case_id>.json`):** A strictly formatted ground-truth annotation containing patient demographics, laboratory layout information, and individual analyte observations.

---

## 2. Dataset Split Taxonomy

The golden dataset is partitioned into four distinct validation splits:

| Split | Target Size | Characteristics & Ingestion Challenges | Target F1 / Pass Rate |
|---|---|---|---|
| **`core/`** | 25 cases | High-resolution, clean digital PDFs across 5 commercial lab layouts (Quest, Labcorp, Apollo, AIIMS, BioReference). Normal, abnormal, and critical ranges. Both conventional (`mg/dL`) and SI (`mmol/L`) units. | $\ge 95\%$ |
| **`hard/`** | 20 cases | Real-world physical capture challenges: scanned noise, rotated skew ($\pm 5^\circ$ to $10^\circ$), low-res blur, mobile camera perspective lighting, and multi-page layouts. | $\ge 85\%$ |
| **`adversarial/`** | 10 cases | Multimodal security attacks: prompt injection in text, white text exploits, physician roleplay commands, system prompt exfiltration attempts. | $100\%$ block rate |
| **`regression/`** | 8+ cases | Historic edge cases: boundary values, borderline ranges, non-numeric titers, zero denominators. | $100\%$ |

---

## 3. Ground-Truth JSON Schema Specification

Each companion JSON must adhere to the following schema:

```json
{
  "case_id": "core_001",
  "patient_name": "Alex Mercer",
  "patient_age": "42",
  "patient_gender": "Male",
  "lab_name": "Quest Diagnostics",
  "layout": "quest",
  "variation": "clean_pdf",
  "unit_system": "mg_dL",
  "report_date": "2026-11-15",
  "tests": [
    {
      "test_name": "Fasting Blood Glucose",
      "value": 145.0,
      "unit": "mg/dL",
      "ref_low": 70.0,
      "ref_high": 99.0,
      "flag": "high",
      "category": "Metabolic"
    }
  ]
}
```

---

## 4. Analyte Naming & Canonical Normalization

Analytes must be annotated with their standard clinical title. The evaluation harness matches analytes using canonical synonym lookup:

| Canonical Analyte Name | Accepted Report Synonyms | Standard LOINC Code |
|---|---|---|
| **Fasting Blood Glucose** | Glucose Fasting, Blood Sugar Fasting, FBS | `1558-6` |
| **Total Cholesterol** | Serum Cholesterol, Chol Total | `2093-3` |
| **Triglycerides** | Triglyceride, TG, Serum Triglycerides | `2571-8` |
| **HDL Cholesterol** | High-Density Lipoprotein, HDL-C | `2085-9` |
| **LDL Cholesterol** | Low-Density Lipoprotein, LDL-C | `13457-7` |
| **Hemoglobin** | Hb, Hgb, Total Hemoglobin | `718-7` |
| **Blood Urea Nitrogen** | BUN, Urea Nitrogen | `3094-0` |
| **Serum Creatinine** | Creatinine, S. Creatinine | `2160-0` |
| **Alkaline Phosphatase** | ALP, Alk Phos | `6768-6` |
| **Total Bilirubin** | Bilirubin Total, T. Bili | `1975-2` |

---

## 5. Reference Range & Deterministic Flagging Rules

Flags must be derived **strictly mathematically** from reference intervals. Human annotators and automated evaluators must apply the following deterministic decision boundary:

1. **`normal`:** `ref_low <= value <= ref_high`
2. **`low`:** `value < ref_low` and `value > panic_low`
3. **`high`:** `value > ref_high` and `value < panic_high`
4. **`critical_low`:** `value <= panic_low` (Panic Value Alert triggered)
5. **`critical_high`:** `value >= panic_high` (Panic Value Alert triggered)
6. **`unknown`:** Reference interval is missing, incomplete, or unparseable.

> **Clinical Safety Mandate:** Under no circumstances should an LLM assign or modify flags. All flags are computed deterministically.

---

## 6. Evaluation Metric Tolerances

When evaluating pipeline extraction against ground truth:

- **Numeric Exact Match:** Measured values match if $|V_{\text{extracted}} - V_{\text{ground\_truth}}| \le 0.05$.
- **Unit Equivalence:** Normalized comparison (`mg/dl` $\equiv$ `mg/dL`, `g/dl` $\equiv$ `g/dL`, `mmol/l` $\equiv$ `mmol/L`).
- **Flag Precision/Recall:** Exact string match of flag category (`normal`, `low`, `high`, `critical_low`, `critical_high`).
- **Critical Error Definition:** Any test result where a measured value is incorrect by $> 5\%$ or where an abnormal/critical flag is misclassified as `normal`.
