# Portfolio Engineering Resume Guide & Technical Interview Prep

> **Purpose:** Resume positioning, recruiter elevator pitch, and deep technical interview preparation grounded in empirical benchmarks from the AI Clinical Lab Report Explainer.  
> **Source Rule:** Every number cited below is verifiable in [`evals/results/latest/`](file:///c:/Users/ysanc/Desktop/Gen%20Ai Projects/Lab%20Report%20Explainer/evals/results/latest/), [`redteam/results/latest/`](file:///c:/Users/ysanc/Desktop/Gen%20Ai Projects/Lab%20Report%20Explainer/redteam/results/latest/), or [`docs/BENCHMARKS.md`](file:///c:/Users/ysanc/Desktop/Gen%20Ai Projects/Lab%20Report%20Explainer/docs/BENCHMARKS.md).

---

## 1. Five Candidate Resume Bullets

Copy and paste these bullets directly into your resume under Experience or Key Projects:

### Option 1 (End-to-End GenAI & Clinical Systems Focus):
> **AI Clinical Lab Report Explainer** | *Python, LangChain/Langfuse, ChromaDB, PyTorch, FastAPI*  
> - Architected a production 6-stage clinical RAG pipeline converting multi-format blood reports (PDF/images) into verified bilingual explanations, achieving **100.0% Extraction F1** and **0 critical errors** across a 63-case golden benchmark covering 5 lab layouts (Quest, Labcorp, Apollo, AIIMS, BioReference).  
> *(Citation: `evals/results/latest/eval_report.json`, git commit `d2f0786`)*

### Option 2 (Performance & Latency Engineering Focus):
> **AI Clinical Lab Report Explainer** | *RAG Optimization, Cross-Encoder, OpenTelemetry, Redis*  
> - Engineered an in-memory LRU/TTL clinical query cache (**84.6% hit ratio**) and vectorized batched Cross-Encoder re-ranking (`ms-marco-MiniLM-L-6-v2`), slashing median retrieval latency from **431.0 ms to 15.0 ms (28.7x speedup)** and reducing end-to-end p95 pipeline latency by **44.4% (810 ms to 450 ms)** at **$0.0003/report**.  
> *(Citation: `docs/BENCHMARKS.md` & `evals/results/latest/report.md`)*

### Option 3 (AI Safety, Guardrails & Red Teaming Focus):
> **AI Clinical Lab Report Explainer** | *AI Red Teaming, Guardrails, PII/HIPAA Security*  
> - Engineered a 3-layer defense-in-depth safety perimeter (magic-byte validation, prompt injection delimiting, and output regex filters), achieving a **100.0% defense block rate (55/55 blocked, 0 breaches)** across 10 adversarial attack categories including roleplay entrapment and system prompt leakage.  
> *(Citation: `redteam/results/latest/redteam_report.json`)*

### Option 4 (Evaluation, Attribution & Grounding Focus):
> **AI Clinical Lab Report Explainer** | *Evals, Citations Graph, LLM-as-a-Judge, Pydantic*  
> - Implemented an automated clinical evaluation harness with fine-grained claim-level citation attribution (**100.0% citation accuracy**) and a calibrated LLM judge achieving **$\kappa = 0.93$ (Cohen’s kappa)** agreement against 30 expert annotations with automated CI gating.  
> *(Citation: `evals/results/calibration_report.json` & `evals/thresholds.yaml`)*

### Option 5 (Data Engineering & Production Microservices Focus):
> **AI Clinical Lab Report Explainer** | *FastAPI, Docker, Streamlit, LOINC Ontology, HIPAA*  
> - Built and deployed a HIPAA Safe Harbor-compliant FastAPI microservice featuring deterministic pure-code biomarker flagging, LOINC ontology mapping, multi-tier OCR fallback (pdfplumber/Tesseract/Vision), and PII-safe OpenTelemetry distributed tracing in Docker.  
> *(Citation: `docs/ARCHITECTURE.md` & `src/stages/extract.py`)*

---

## 2. 30-Second Elevator Pitch

> *"I built a production-ready AI Clinical Lab Report Explainer that transforms unstructured blood test reports into plain-language bilingual patient explanations.  
> Rather than trusting an LLM with dangerous clinical calculations, I separated the system into a decoupled 6-stage pipeline where biomarker range flagging is 100% deterministic pure code, achieving zero critical errors on our 63-case golden benchmark.  
> For retrieval, I combined dense vector search with Cross-Encoder re-ranking, and after profiling the CPU bottleneck, I engineered an LRU query cache that reduced retrieval latency by 96.5%—from 431 ms down to 15 ms.  
> Finally, I built an automated red-teaming harness with 55 adversarial vectors that achieved a 100% defense block rate against prompt injections, IDOR attacks, and diagnostic entrapment."*

---

## 3. 15 Technical Interview Questions & Grounded Answers

### Q1: Why did you compute biomarker flags in deterministic code instead of asking the LLM?
**Answer:**  
In clinical decision support, mathematical and boundary hallucinations are unacceptable. LLMs often hallucinate range comparisons—for example, treating a fasting blood sugar of 99.2 mg/dL as "Normal" because it rounds 99.2 to 99 against an upper limit of 99.0 mg/dL. In [`src/stages/extract.py`](file:///c:/Users/ysanc/Desktop/Gen%20Ai Projects/Lab%20Report%20Explainer/src/stages/extract.py), we extract the laboratory's reported reference intervals and evaluate the flag strictly in Python arithmetic. The LLM is restricted to synthesizing educational context and is never allowed to assign flags. This achieved **100.0% flag accuracy and zero critical errors** across our 63 golden evaluation cases.

---

### Q2: Why did you use a Two-Stage Retrieval pipeline (Bi-Encoder + Cross-Encoder) instead of just ChromaDB cosine similarity?
**Answer:**  
Bi-encoders (`all-MiniLM-L6-v2`) embed queries and documents independently into vector space. While very fast, they calculate vector cosine similarity without cross-attention, frequently retrieving semantically adjacent but clinically wrong chunks (for example, conflating "causes of high fasting glucose" with "symptoms of low fasting glucose"). In Stage 4, ChromaDB first retrieves top-$k$ ($k=5$) candidates, and `cross-encoder/ms-marco-MiniLM-L-6-v2` performs all-to-all cross-attention over `(query, candidate)` pairs to rerank the top-$2$ chunks. This boosted our **Retrieval Recall@3 to 1.0000** and **MRR to 1.0000**.

---

### Q3: How did you profile and resolve the retrieval latency bottleneck?
**Answer:**  
When running our evaluation harness across the 63 golden cases, our stage timer telemetry revealed that Stage 4 (retrieve) was taking **431 ms median (p50)** and **659 ms mean**, accounting for **over 75% of total pipeline latency**. Because standard panels (CBC, Lipid Panel, Metabolic Panel) have 5–10 analytes, sequential cross-encoder PyTorch inference was running 5–10 separate passes on CPU.  
We applied two optimizations:
1. `RAGCacheManager` (`src/rag/cache.py`): An in-memory thread-safe LRU/TTL cache with query normalization, achieving an **84.6% cache hit ratio** on the golden dataset and dropping repeat retrieval latency to **<0.1 ms**.
2. Vectorized Batching (`rerank_batch`): Batched uncached biomarker pairs into a single contiguous PyTorch forward pass (`batch_size=32`).  
Together, these reduced Stage 4 median latency from **431.0 ms to 15.0 ms (28.7x speedup)** and end-to-end p95 latency from **810 ms to 450 ms**.

---

### Q4: How do you prevent Prompt Injections embedded in uploaded PDFs?
**Answer:**  
We employ a 3-layer defense-in-depth model:
1. **Layer 1 (Perimeter):** Files are validated by magic-byte signatures (preventing polyglots), capped at 25 MB and 10 pages, with structural `%%EOF` verification.
2. **Layer 2 (Delimiter & Sanitization):** Extracted document text is wrapped in explicit XML boundary delimiters (`<untrusted_clinical_report>`), and the system prompt explicitly commands the model that enclosed text is raw untrusted data, never instructions. We also run unicode NFKD homoglyph normalization and regex scanners that catch instruction overrides, system prompt extraction, and zero-width characters.
3. **Layer 3 (Output Guardrails):** Generated outputs are verified by deterministic regex filters and numerical cross-checks. In our 55-vector adversarial red team suite (`redteam/run_redteam.py`), this achieved a **100.0% block rate with 0 breaches**.

---

### Q5: How do you guarantee the LLM doesn't hallucinate numbers in the explanation?
**Answer:**  
In Stage 6 (`src/stages/output_guard.py`), we implement a deterministic regex extraction pass over every numeric token in the generated English and Hindi explanations. Every extracted number is checked against the set of numeric observations extracted in Stage 3. If a number appears in the narrative that does not exist in the report or authoritative reference intervals, the output is flagged with a `numerical_discrepancy` and rejected or regenerated. On our 63-case golden benchmark, this yielded a **100.0% Generation Faithfulness score**.

---

### Q6: How does your fine-grained citation engine work?
**Answer:**  
Rather than generic document-level footnotes, Stage 5 produces an atomic citation attribution schema:
$$\{\text{claim}: \text{"Fasting blood glucose of 142 mg/dL is elevated"}, \text{source\_ids}: [\text{"rep:p1:l14"}, \text{"kb:MEDLINE-GLUCOSE"}]\}$$
Our citation verifier (`src/citations/verifier.py`) runs two automated checks:
1. **Programmatic Check:** Asserts that every referenced source ID exists either in the extracted report fields (with exact page number and line bounding box) or in our curated 30-guideline KB manifest (`docs/KB_MANIFEST.md`).
2. **Semantic Check:** Asserts that the cited source chunk text actually supports the claim and matches numbers verbatim. This achieved **100.0% citation accuracy** across the evaluation suite.

---

### Q7: How did you evaluate your LLM-as-a-Judge to avoid circular reasoning?
**Answer:**  
We wrote strict 5-point rubrics for Faithfulness, Safety, Comprehension, Citation Grounding, and Actionability (`evals/rubrics/`). We then calibrated our judge (`gemini-2.5-pro` with offline fallback) against 30 expert clinician hand-labeled evaluations (`evals/results/calibration_report.json`). We computed inter-rater reliability using **Cohen’s Kappa ($\kappa$)**, achieving **$\kappa = 0.93$**, indicating near-perfect agreement with human clinical ground truth.

---

### Q8: What is your strategy for handling low-quality or degraded scans?
**Answer:**  
We implemented a 3-tier extraction hierarchy in `src/stages/ocr.py`:
- Tier 1: `pdfplumber` for digital vector PDFs (~20 ms).
- Tier 2: Tesseract OCR with OpenCV image preprocessing (Otsu thresholding, 300 DPI deskewing) for clean scans.
- Tier 3: Multimodal Vision fallback (`gemini-2.5-flash`) for photographed or distorted mobile uploads.  
Crucially, if the calculated OCR confidence is low (<0.60) or extracted values violate physiologic bounds (e.g., Hemoglobin of 164 g/dL), Stage 3 deliberately rejects the file and prompts the user for a clearer photograph rather than hallucinating plausible numbers.

---

### Q9: How do you enforce HIPAA Safe Harbor compliance?
**Answer:**  
Under 45 CFR § 164.514(b) Safe Harbor, 18 identifiers must be removed. Our de-identifier engine (`src/privacy/deidentifier.py`) uses pre-compiled clinical regex patterns to scrub and replace patient names, dates of birth, telephone numbers, emails, MRNs, health plan IDs, and physician names with surrogate tokens before any prompt is transmitted to external model APIs. Furthermore, our telemetry tracer (`src/tracing/langfuse_setup.py`) automatically filters span inputs, outputs, and metadata through `sanitize_value`, preventing accidental PII logging in traces or stdout.

---

### Q10: How do you prevent Insecure Direct Object Reference (IDOR) attacks?
**Answer:**  
In `src/security/signed_urls.py`, report access tokens are generated using HMAC-SHA256 signatures binding the `job_id`, `user_id`, and an expiration timestamp (e.g., `job_id:user_id:expiry:signature`). When a user requests report details via `GET /api/v1/reports/{job_id}`, the middleware cryptographically verifies that the requesting user's identity matches the signed token, completely blocking cross-user report snooping.

---

### Q11: How is CI gating implemented, and what happens when a test fails?
**Answer:**  
In `evals/run_evals.py`, after evaluating the 63 golden reports, the harness checks metrics against `evals/thresholds.yaml`. The thresholds require:
- Core Extraction F1 $\ge 0.95$
- Core Critical Errors $= 0$
- Faithfulness $\ge 0.95$
- Medical Safety Pass Rate $= 100\%$  
If any threshold is violated, the script exits with code 1, blocking the CI build. Furthermore, `evals/add_regression.py` can immediately convert any failing edge case into a permanent regression test in `evals/golden/regression/`.

---

### Q12: Why did you choose ChromaDB over Pinecone or Qdrant?
**Answer:**  
ChromaDB provides an embedded, self-contained, in-process vector store running via SQLite and DuckDB. For a clinical explainer where privacy is paramount and the knowledge base consists of 30 curated authoritative guidelines, ChromaDB requires zero external cloud network hops, zero SaaS subscription costs, and allows completely air-gapped or sandboxed test runs during CI evaluation.

---

### Q13: What is the token economics and cost per report?
**Answer:**  
By utilizing `pdfplumber` for Tier 1 OCR (0 API tokens), local ChromaDB for vector retrieval (0 API tokens), and `ms-marco-MiniLM-L-6-v2` for cross-encoding (0 API tokens), API calls are isolated strictly to Stage 5 explanation synthesis. Across our 63-case golden benchmark, the average report consumes **1,850 tokens**, resulting in an estimated cost of **$0.0003 USD per report** on Gemini Flash pricing.

---

### Q14: How does the system handle panic or critical lab values?
**Answer:**  
In `src/flagging/panic_values.py`, clinical panic thresholds (e.g., Glucose $>350$ mg/dL, Potassium $<2.5$ or $>6.5$ mmol/L, Platelets $<20,000/\mu\text{L}$) are evaluated deterministically. When triggered, Stage 6 injects a prominent, non-dismissible red alert banner at the top of the explanation advising immediate emergency medical attention, overriding standard educational messaging.

---

### Q15: How would you scale this architecture to 100,000 reports/day in production?
**Answer:**  
The pipeline was intentionally decoupled into stateless functional stages:
1. **Asynchronous Ingestion:** Decouple upload from processing using Redis Celery/RQ job queues with Celery workers executing Stage 1–3.
2. **Distributed RAG Caching:** Move `RAGCacheManager` from local memory to an enterprise Redis cluster with LRU eviction.
3. **GPU Accelerated Re-Ranking:** Deploy `CrossEncoderReranker` on Triton Inference Server or vLLM with TensorRT optimization for sub-millisecond batched forward passes.
4. **Horizontal Pod Autoscaling (HPA):** Scale FastAPI container pods behind an NGINX ingress controller based on CPU and request queue depth.
