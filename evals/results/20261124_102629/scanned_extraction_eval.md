# Scanned Report Extraction Benchmark Results

- **Timestamp:** `20261124_102629`
- **Git Commit Hash:** `679c619965dcf0631416bf36928a065f05319663`
- **Multimodal Vision Model:** `gemini-3.5-flash`
- **Flagging Engine:** `Flagger (Deterministic Python Mathematical Interval)`

## Summary Metrics

| Metric | Result |
| :--- | :--- |
| **Field-Level Precision** | 100.00% |
| **Field-Level Recall** | 100.00% |
| **Field-Level F1 Score** | 1.0000 |
| **Numeric Exact-Match Accuracy** | 100.00% (23/23) |
| **Unit Extraction Accuracy** | 100.00% (23/23) |
| **Deterministic Flag Accuracy** | 100.00% (23/23) |
| **Critical Clinical Errors** | **0** (wrong number or flag) |

## Per-Condition Performance Breakdown

| Condition | Fixture | GT Tests | Extracted | F1 | Numeric Match | Flag Accuracy | Critical Errors | Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `image_only_pdf` | `scanned_clean.pdf` | 4 | 4 | 1.00 | 100.0% | 100.0% | 0 | 21.19s |
| `photographed_noisy` | `scanned_noisy.png` | 4 | 4 | 1.00 | 100.0% | 100.0% | 0 | 22.12s |
| `rotated_90_deg` | `scanned_rotated.png` | 4 | 4 | 1.00 | 100.0% | 100.0% | 0 | 45.89s |
| `skewed_7_deg` | `scanned_skewed.png` | 4 | 4 | 1.00 | 100.0% | 100.0% | 0 | 20.9s |
| `low_resolution_downsampled` | `scanned_lowres.png` | 3 | 3 | 1.00 | 100.0% | 100.0% | 0 | 12.9s |
| `multipage_image_only_pdf` | `scanned_multipage.pdf` | 4 | 4 | 1.00 | 100.0% | 100.0% | 0 | 77.56s |
