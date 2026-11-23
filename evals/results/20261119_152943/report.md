# Clinical Evaluation & Benchmark Report

![CI Status: FAIL](https://img.shields.io/badge/CI_Evals-FAIL-red)
- **Run Timestamp:** `2026-11-19T09:59:43.725147+00:00`
- **Git Commit Hash:** `59c3596`
- **Total Test Reports:** `63`
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
| **Readability (FKGL)** | $\le 10.0$ (Grade Level) | **9.7** | PASS |
| **End-to-End Latency (p95)** | $\le 25.0\text{ s}$ | **0.79 s** | PASS |

---

## 2. Performance Breakdown by Golden Split

| Split Name | Cases | Ext. F1 | Numeric Match | Flag Acc. | Critical Errors | Safety Pass Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Core** | 25 | 1.0000 | 100.0% | 97.3% | 0 | 100.0% |
| **Hard** | 20 | 1.0000 | 100.0% | 99.0% | 0 | 100.0% |
| **Adversarial** | 10 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |
| **Regression** | 8 | 1.0000 | 100.0% | 100.0% | 0 | 100.0% |

---

## 3. Extraction Accuracy by Lab Layout

| Lab Layout | Sample Count | Precision | Recall | F1-Score | Numeric Match | Flag Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Aiims** | 12 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 98.6% |
| **Apollo** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 97.2% |
| **Bioreference** | 12 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 98.6% |
| **Labcorp** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 100.0% |
| **Quest** | 13 | 1.0000 | 1.0000 | **1.0000** | 100.0% | 98.7% |

---

## 4. Pipeline Stage Latency Profile & Economics

| Stage Name | Median (p50) | 95th Percentile (p95) | Mean Latency |
| :--- | :--- | :--- | :--- |
| **Stage 1: validate_upload** | 2.0 ms | 2.0 ms | 1.0 ms |
| **Stage 2: ocr_parse** | 31.0 ms | 45.0 ms | 28.0 ms |
| **Stage 3: extract_values** | 32.0 ms | 48.0 ms | 33.0 ms |
| **Stage 4: retrieve (RAG)** | 427.0 ms | 519.0 ms | 696.0 ms |
| **Stage 5: explain (LLM)** | 103.0 ms | 190.0 ms | 106.0 ms |
| **Stage 6: output_guard** | 2.0 ms | 3.0 ms | 2.0 ms |
| **End-to-End Pipeline** | **0.59 s** | **0.79 s** | **0.87 s** |

- **Estimated Cost per Report:** `$0.0003 USD`
- **Estimated Average Tokens:** `1850` tokens/report

---

## 5. CI Gating Violations

**The following thresholds were violated:**
- ❌ `Core Flag Accuracy 0.9733 < min 0.98`
