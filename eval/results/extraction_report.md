# 📊 PDF Extraction Evaluation Report

> **Target F1:** ≥ 90.0% | **Status:** ✅ PASS

---

## 1. Overall Performance Metrics

| Metric | Measured Score | Evaluation Target | Status |
|---|---|---|---|
| **Analyte F1 Score** | **100.0%** | ≥ 90.0% | ✅ PASS |
| **Analyte Precision** | **100.0%** | ≥ 95.0% | ✅ |
| **Analyte Recall** | **100.0%** | ≥ 90.0% | ✅ |
| **Value Accuracy** | **100.0%** | ≥ 95.0% | ✅ |
| **Unit Accuracy** | **98.4%** | ≥ 90.0% | ✅ |
| **Reference Range Accuracy** | **100.0%** | ≥ 85.0% | ✅ |

---

## 2. Per-Report Breakdown

| Report File | Extractor Used | Ground Truth | Extracted | Matched | Value Acc | Range Acc |
|---|---|---|---|---|---|---|
| `complex_borders.pdf` | `pdfplumber` | 6 | 6 | 6 | 100% | 100% |
| `lal_pathlabs_thyroid.pdf` | `pdfplumber` | 5 | 5 | 5 | 100% | 100% |
| `metropolis_liver.pdf` | `pdfplumber` | 7 | 7 | 7 | 100% | 100% |
| `multipage_full_body.pdf` | `pdfplumber` | 13 | 13 | 13 | 100% | 100% |
| `non_numeric.pdf` | `pdfplumber` | 7 | 7 | 7 | 100% | 100% |
| `scanned_report.pdf` | `pdfplumber` | 4 | 4 | 4 | 100% | 100% |
| `srl_diabetes.pdf` | `pdfplumber` | 4 | 4 | 4 | 100% | 100% |
| `srl_lipid_panel.pdf` | `pdfplumber` | 5 | 5 | 5 | 100% | 100% |
| `thyrocare_cbc.pdf` | `pdfplumber` | 8 | 8 | 8 | 100% | 100% |
| `thyrocare_kidney.pdf` | `pdfplumber` | 5 | 5 | 5 | 100% | 100% |
