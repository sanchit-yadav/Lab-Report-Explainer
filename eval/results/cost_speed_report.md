# ⏱️ Cost & Latency Benchmark Report

> **Average Cost per Report:** $0.00160 USD | **p50 Latency:** 0.67s | **Status:** ✅ PASS

---

## 1. Executive Summary Metrics

| Metric | Measured Result | Evaluation Target | Status |
|---|---|---|---|
| **Average Cost per Report** | **$0.00160 USD** | ≤ $0.0100 USD | ✅ PASS |
| **Total Benchmark Cost (10 Reports)** | **$0.01603 USD** | — | ✅ PASS |
| **Reports Processed per $1.00** | **~624 reports** | ≥ 100 reports | ✅ PASS |
| **Median Latency (p50)** | **0.67 seconds** | ≤ 10.0 seconds | ✅ PASS |
| **95th Percentile Latency (p95)** | **1.52 seconds** | ≤ 15.0 seconds | ✅ PASS |
| **Peak Latency (p99)** | **1.52 seconds** | — | ✅ |
| **Average Input Tokens / Report** | **1190 tokens** | — | ✅ |
| **Average Output Tokens / Report** | **870 tokens** | — | ✅ |

---

## 2. Per-Report Latency and Cost Breakdown

| Report File | Analyzed Tests | Flagged Explained | Latency | Tokens | Cost (USD) |
|---|---|---|---|---|---|
| `complex_borders.pdf` | 6 | 0 | 0.06s | 300 | $0.00020 |
| `lal_pathlabs_thyroid.pdf` | 5 | 1 | 0.57s | 1100 | $0.00084 |
| `metropolis_liver.pdf` | 7 | 4 | 1.31s | 3500 | $0.00275 |
| `multipage_full_body.pdf` | 13 | 2 | 0.67s | 1900 | $0.00148 |
| `non_numeric.pdf` | 7 | 0 | 0.04s | 300 | $0.00020 |
| `scanned_report.pdf` | 4 | 3 | 0.91s | 2700 | $0.00211 |
| `srl_diabetes.pdf` | 4 | 4 | 1.35s | 3500 | $0.00275 |
| `srl_lipid_panel.pdf` | 5 | 5 | 1.52s | 4300 | $0.00339 |
| `thyrocare_cbc.pdf` | 8 | 1 | 0.35s | 1100 | $0.00084 |
| `thyrocare_kidney.pdf` | 5 | 2 | 0.66s | 1900 | $0.00148 |

---

## 3. Resume & Interview Highlights

> "By utilizing `gemini-3.1-flash-lite` for clinical explanation and local caching for cross-encoder re-ranking,
> our end-to-end pipeline operates at an average cost of **$0.00160 per report** (~624 reports per dollar)
> with a median latency of **0.67 seconds**, making it commercially viable for large-scale production."
