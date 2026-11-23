# Clinical Evaluation & Benchmark Report

![CI Status: FAIL](https://img.shields.io/badge/CI_Evals-FAIL-red)
- **Run Timestamp:** `2026-11-19T09:52:51.401366+00:00`
- **Git Commit Hash:** `59c3596`
- **Total Test Reports:** `8`
- **Models:** Explainer: `gemini-2.5-flash (with offline fallback)` | Judge: `gemini-2.5-pro / calibrated rubric rule engine`

---

## 1. Executive Summary & Gating Status

| Evaluation Dimension | Metric Target | Measured Result | CI Status |
| :--- | :--- | :--- | :--- |
| **Core Extraction F1** | $\ge 0.95$ | **1.0000** | PASS |
| **Core Critical Errors** | $0$ | **0** | PASS |
| **RAG Retrieval Recall@3** | $\ge 0.90$ | **0.8000** | FAIL |
| **Retrieval MRR** | $\ge 0.85$ | **0.7750** | FAIL |
| **Generation Faithfulness** | $\ge 0.95$ | **0.7500** | FAIL |
| **Medical Safety Pass Rate** | $1.00$ ($100\%$) | **100.0\%** | PASS |
| **Readability (FKGL)** | $\le 10.0$ (Grade Level) | **13.2** | FAIL |
| **End-to-End Latency (p95)** | $\le 25.0\text{ s}$ | **12.58 s** | PASS |

---

## 2. Performance Breakdown by Golden Split

| Split Name | Cases | Ext. F1 | Numeric Match | Flag Acc. | Critical Errors | Safety Pass Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Core** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Hard** | 2 | 0.0000 | 0.0% | 0.0% | 0 | 100.0% |
| **Adversarial** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Regression** | 2 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |

---

## 3. Extraction Accuracy by Lab Layout

| Lab Layout | Sample Count | Precision | Recall | F1-Score | Numeric Match | Flag Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Labcorp** | 4 | 0.7500 | 0.7500 | **0.7500** | 75.0% | 75.0% |
| **Quest** | 4 | 0.7500 | 0.7500 | **0.7500** | 75.0% | 75.0% |

---

## 4. Pipeline Stage Latency Profile & Economics

| Stage Name | Median (p50) | 95th Percentile (p95) | Mean Latency |
| :--- | :--- | :--- | :--- |
| **Stage 1: validate_upload** | 2.0 ms | 3.0 ms | 1.0 ms |
| **Stage 2: ocr_parse** | 29.0 ms | 38.0 ms | 24.0 ms |
| **Stage 3: extract_values** | 33.0 ms | 62.0 ms | 37.0 ms |
| **Stage 4: retrieve (RAG)** | 342.0 ms | 12254.0 ms | 2721.0 ms |
| **Stage 5: explain (LLM)** | 63.0 ms | 226.0 ms | 79.0 ms |
| **Stage 6: output_guard** | 1.0 ms | 4.0 ms | 2.0 ms |
| **End-to-End Pipeline** | **0.50 s** | **12.58 s** | **2.87 s** |

- **Estimated Cost per Report:** `$0.0003 USD`
- **Estimated Average Tokens:** `1850` tokens/report

---

## 5. CI Gating Violations

**The following thresholds were violated:**
- ❌ `Hard F1 0.0000 < min 0.8`
- ❌ `Retrieval Recall@3 0.8000 < min 0.9`
- ❌ `Retrieval MRR 0.7750 < min 0.85`
- ❌ `Generation Faithfulness 0.7500 < min 0.95`
- ❌ `Readability Grade 13.17 > max 10.0`
