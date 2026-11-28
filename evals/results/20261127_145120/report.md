# Clinical Evaluation & Benchmark Report

![CI Status: PASS](https://img.shields.io/badge/CI_Evals-PASS-brightgreen)
- **Run Timestamp:** `2026-11-27T09:21:20.578978+00:00`
- **Git Commit Hash:** `85854b3`
- **Total Test Reports:** `63`
- **Models Used (Live):** `gemini-3.5-flash-lite (69x)` | **Configured Explainer/Vision:** `gemini-3.5-flash-lite` | **Judge:** `ClinicalJudge (calibrated rubric engine)`

---

## 1. Executive Summary & Gating Status

| Evaluation Dimension | Metric Target | Measured Result | CI Status |
| :--- | :--- | :--- | :--- |
| **Upload Rejection Accuracy** | $1.00$ ($100\%$) | **100.0\%** | PASS |
| **Core Extraction F1** | $\ge 0.95$ | **1.0000** | PASS |
| **Core Critical Errors** | $0$ | **0** | PASS |
| **RAG Retrieval Recall@3** | $\ge 0.90$ | **1.0000** | PASS |
| **RAG Retrieval Recall@10** | $\ge 0.95$ | **1.0000** | PASS |
| **Retrieval MRR** | $\ge 0.85$ | **1.0000** | PASS |
| **Generation Faithfulness** | $\ge 0.95$ | **1.0000** | PASS |
| **Medical Safety Pass Rate** | $1.00$ ($100\%$) | **100.0\%** | PASS |
| **Citation Accuracy** | $\ge 0.90$ ($90\%$) | **100.0\%** | PASS |
| **Readability (FKGL)** | $\le 12.0$ (Grade Level) | **6.6** | PASS |
| **End-to-End Latency (p95)** | $\le 45.0\text{ s}$ | **8.85 s** | PASS |

---

## 2. Stage 1: Upload Validation Battery

| Test Vector | Category | Expected | Actual | Pass/Fail | Latency | Rejection Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `zero_byte.pdf` | empty_file | Reject | Reject | PASS | 0.51 ms | Uploaded file is empty (0 bytes). |
| `corrupt_header.pdf` | corrupt_header | Reject | Reject | PASS | 0.24 ms | File failed magic-byte validation. Only PDF, PNG, JPG, and WebP are accepted. |
| `truncated_pdf.pdf` | truncated_pdf | Reject | Reject | PASS | 0.46 ms | Corrupted or truncated PDF structure: missing %%EOF marker. |
| `exe_disguised_as_pdf.pdf` | executable_pe | Reject | Reject | PASS | 0.17 ms | File failed magic-byte validation. Only PDF, PNG, JPG, and WebP are accepted. |
| `elf_binary.pdf` | executable_elf | Reject | Reject | PASS | 0.15 ms | File failed magic-byte validation. Only PDF, PNG, JPG, and WebP are accepted. |
| `unsupported_ext.sh` | unsupported_extension | Reject | Reject | PASS | 0.19 ms | File failed magic-byte validation. Only PDF, PNG, JPG, and WebP are accepted. |
| `oversized.pdf` | oversized_file | Reject | Reject | PASS | 23.56 ms | File exceeds maximum allowed size of 25 MB. |
| `valid_clean_report.pdf` | valid_pdf | Valid | Valid | PASS | 2.91 ms | Accepted |
| `valid_png_header.png` | valid_png | Valid | Valid | PASS | 0.26 ms | Accepted |
| `valid_jpeg_header.jpg` | valid_jpeg | Valid | Valid | PASS | 0.17 ms | Accepted |

---

## 3. Performance Breakdown by Golden Split

| Split Name | Cases | Ext. F1 | Numeric Match | Flag Acc. | Critical Errors | Safety Pass Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Core** | 25 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Hard** | 20 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Adversarial** | 10 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Regression** | 8 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |

---

## 4. Extraction Accuracy by Document Condition

| Condition / Variation | Sample Count | Precision | Recall | F1-Score | Numeric Match | Flag Accuracy | Critical Errors |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Blurry** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |
| **Clean Pdf** | 43 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |
| **Multipage** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |
| **Photographed** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |
| **Rotated** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |
| **Scanned** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% | 0 |

---

## 5. Extraction Accuracy by Lab Layout

| Lab Layout | Sample Count | Precision | Recall | F1-Score | Numeric Match | Flag Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Aiims** | 12 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Apollo** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Bioreference** | 12 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Labcorp** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Quest** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |

---

## 6. Pipeline Stage Latency Profile & Economics

| Stage Name | Median (p50) | 95th Percentile (p95) | Mean Latency |
| :--- | :--- | :--- | :--- |
| **Stage 1: validate_upload** | 2.0 ms | 4.0 ms | 2.0 ms |
| **Stage 2: ocr_parse** | 48.0 ms | 4648.0 ms | 1173.0 ms |
| **Stage 3: extract_values** | 39.0 ms | 57.0 ms | 32.0 ms |
| **Stage 4: retrieve (RAG)** | 25.0 ms | 1433.0 ms | 349.0 ms |
| **Stage 5: explain (LLM)** | 3162.0 ms | 4788.0 ms | 3021.0 ms |
| **Stage 6: output_guard** | 3.0 ms | 6.0 ms | 3.0 ms |
| **End-to-End Pipeline** | **4.49 s** | **8.85 s** | **4.60 s** |

- **Measured Cost per Report:** `$0.00068 USD` (69 total API calls)
- **Measured Average Tokens:** `3067.0` tokens/report (`1826.5` input + `1240.5` output)

---

## 7. Clinical LLM Judge Calibration & Human Agreement

- **Calibration Dataset:** 30 Hand-Labeled Gold Standard Reports
- **Quadratic Weighted Kappa (κ):** `0.9364` (`evals/results/calibration_report.json`)
- **Unweighted Cohen's Kappa:** `0.839`
- **Composite Score MAE:** `0.3117`
- **Scoring Rubric:** `/evals/rubrics/generation_rubric.md` (Faithfulness 30%, Safety 30%, Comprehension 15%, Citation 15%, Actionability 10%)

---

## 8. CI Gating Violations

**Zero violations detected.** All metrics meet or exceed production thresholds defined in `/evals/thresholds.yaml`.
