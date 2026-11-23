# Clinical Evaluation & Benchmark Report

![CI Status: PASS](https://img.shields.io/badge/CI_Evals-PASS-brightgreen)
- **Run Timestamp:** `2026-11-19T09:58:30.836991+00:00`
- **Git Commit Hash:** `59c3596`
- **Total Test Reports:** `8`
- **Models:** Explainer: `gemini-2.5-flash (with offline fallback)` | Judge: `gemini-2.5-pro / calibrated rubric rule engine`

---

## 1. Executive Summary & Gating Status

| Evaluation Dimension | Metric Target | Measured Result | CI Status |
| :--- | :--- | :--- | :--- |
| **Core Extraction F1** | $\ge 0.95$ | **1.0000** | PASS |
| **Core Critical Errors** | $0$ | **0** | PASS |
| **RAG Retrieval Recall@3** | $\ge 0.90$ | **1.0000** | PASS |
| **Retrieval MRR** | $\ge 0.85$ | **1.0000** | PASS |
| **Generation Faithfulness** | $\ge 0.95$ | **1.0000** | PASS |
| **Medical Safety Pass Rate** | $1.00$ ($100\%$) | **100.0\%** | PASS |
| **Readability (FKGL)** | $\le 10.0$ (Grade Level) | **9.4** | PASS |
| **End-to-End Latency (p95)** | $\le 25.0\text{ s}$ | **15.30 s** | PASS |

---

## 2. Performance Breakdown by Golden Split

| Split Name | Cases | Ext. F1 | Numeric Match | Flag Acc. | Critical Errors | Safety Pass Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Core** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Hard** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Adversarial** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Regression** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |

---

## 3. Extraction Accuracy by Lab Layout

| Lab Layout | Sample Count | Precision | Recall | F1-Score | Numeric Match | Flag Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Labcorp** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Quest** | 4 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |

---

## 4. Pipeline Stage Latency Profile & Economics

| Stage Name | Median (p50) | 95th Percentile (p95) | Mean Latency |
| :--- | :--- | :--- | :--- |
| **Stage 1: validate_upload** | 2.0 ms | 3.0 ms | 1.0 ms |
| **Stage 2: ocr_parse** | 29.0 ms | 51.0 ms | 31.0 ms |
| **Stage 3: extract_values** | 36.0 ms | 60.0 ms | 36.0 ms |
| **Stage 4: retrieve (RAG)** | 426.0 ms | 14965.0 ms | 3371.0 ms |
| **Stage 5: explain (LLM)** | 95.0 ms | 227.0 ms | 113.0 ms |
| **Stage 6: output_guard** | 2.0 ms | 3.0 ms | 2.0 ms |
| **End-to-End Pipeline** | **0.59 s** | **15.30 s** | **3.56 s** |

- **Estimated Cost per Report:** `$0.0003 USD`
- **Estimated Average Tokens:** `1850` tokens/report

---

## 5. CI Gating Violations

**Zero violations detected.** All metrics meet or exceed production thresholds defined in `/evals/thresholds.yaml`.
