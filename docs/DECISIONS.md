# Architectural Decision Records (ADRs)

> **Context:** Engineering trade-offs, model selections, and architectural decisions made while developing the AI Clinical Lab Report Explainer.

---

## Table of Decisions

- [ADR-001: Pure Deterministic Code Flagging vs. LLM Range Evaluation](#adr-001-pure-deterministic-code-flagging-vs-llm-range-evaluation)
- [ADR-002: Retrieval-Augmented Generation (RAG) vs. Fine-Tuning or Direct Prompting](#adr-002-retrieval-augmented-generation-rag-vs-fine-tuning-or-direct-prompting)
- [ADR-003: Two-Stage Hybrid Retrieval: Bi-Encoder + Cross-Encoder Re-Ranking](#adr-003-two-stage-hybrid-retrieval-bi-encoder--cross-encoder-re-ranking)
- [ADR-004: In-Memory LRU/TTL Clinical RAG Query Caching](#adr-004-in-memory-lruttl-clinical-rag-query-caching)
- [ADR-005: Multi-Tier OCR Parsing Strategy (Digital -> Tesseract -> Multimodal)](#adr-005-multi-tier-ocr-parsing-strategy-digital---tesseract---multimodal)
- [ADR-006: Fine-Grained Claim-Level Citation Attribution vs. Document References](#adr-006-fine-grained-claim-level-citation-attribution-vs-document-references)

---

### ADR-001: Pure Deterministic Code Flagging vs. LLM Range Evaluation

- **Status:** Accepted
- **Context:** Blood tests must be classified into clinical states (`NORMAL`, `LOW`, `HIGH`, `CRITICAL_LOW`, `CRITICAL_HIGH`) by comparing observed values against demographic- and lab-specific reference intervals. LLMs frequently hallucinate boundary comparisons (e.g., classifying 99.2 mg/dL as Normal when the upper limit is 99.0 mg/dL).
- **Decision:** All biomarker flagging is executed in deterministic Python arithmetic inside `src/stages/extract.py` and `src/flagging/flagger.py`. The LLM is strictly prohibited from evaluating or altering clinical flags.
- **Consequences:**
  - *Positive:* 100.0% flag accuracy across all 63 golden evaluation cases; 0 critical errors; zero risk of LLM mathematical hallucinations.
  - *Negative:* Requires explicit regex extraction of reference ranges and handling diverse range syntax (`<100`, `10-30`, `Negative`). Handled via standardized normalizer regexes.

---

### ADR-002: Retrieval-Augmented Generation (RAG) vs. Fine-Tuning or Direct Prompting

- **Status:** Accepted
- **Context:** Medical knowledge evolves constantly (e.g., ADA updates HbA1c prediabetes cutoffs). Direct prompting relies on static parametric weights that hallucinate plausible-sounding pathophysiology, while fine-tuning is expensive, opaque, and difficult to update.
- **Decision:** Implement RAG grounded in an authoritative catalog of 30 curated MedlinePlus / NIH clinical guidelines (`docs/KB_MANIFEST.md`).
- **Consequences:**
  - *Positive:* High faithfulness (1.0000 on eval); fine-grained citation verifiable by users; updating medical guidelines requires merely updating markdown files and re-indexing ChromaDB, without retraining models.
  - *Negative:* Introduces vector retrieval latency (mitigated in Phase 6 with RAG query caching).

---

### ADR-003: Two-Stage Hybrid Retrieval: Bi-Encoder + Cross-Encoder Re-Ranking

- **Status:** Accepted
- **Context:** Bi-encoders (`all-MiniLM-L6-v2`) compute cosine similarity between isolated query and document embeddings. While fast, bi-encoders miss subtle clinical distinctions (e.g., "high fasting glucose causes" vs. "low fasting glucose symptoms").
- **Decision:** Implement a two-stage retrieval pipeline:
  1. ChromaDB bi-encoder retrieval fetches top-$k$ ($k=5$) candidates.
  2. Cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` performs joint all-to-all cross-attention over `(query, document)` pairs, returning top-$n$ ($n=2$) reranked chunks.
- **Consequences:**
  - *Positive:* Recall@3 reached 1.0000; MRR reached 1.0000; eliminates semantically adjacent but clinically irrelevant context chunks.
  - *Negative:* Cross-encoder CPU inference initially added ~430 ms latency per report. Solved via batched vectorization and query caching (ADR-004).

---

### ADR-004: In-Memory LRU/TTL Clinical RAG Query Caching

- **Status:** Accepted
- **Context:** Across large patient populations, ~80% of lab tests belong to standard routine panels (Lipid Panel, CBC, Metabolic Panel). Repeatedly re-ranking identical queries ("Fasting Blood Glucose High lab test meaning") wasted CPU cycles and dominated pipeline runtime.
- **Decision:** Introduce `RAGCacheManager` (`src/rag/cache.py`) implementing a thread-safe LRU cache with a 24-hour TTL and normalized key indexing.
- **Consequences:**
  - *Positive:* Achieved **84.6% cache hit ratio** on the golden benchmark; reduced Stage 4 median latency from **431 ms to 15 ms (28.7x speedup)**; reduced end-to-end median latency from **0.59s to 0.15s (~4x speedup)**.
  - *Negative:* In-memory footprint of ~10 MB for 1000 cached clinical queries (negligible).

---

### ADR-005: Multi-Tier OCR Parsing Strategy (Digital -> Tesseract -> Multimodal)

- **Status:** Accepted
- **Context:** Patients upload lab reports in widely varying formats: clean vector PDFs (from digital patient portals), scanned photocopies, and photographed mobile phone images with shadows and rotation.
- **Decision:** Implement a tiered extraction fallback:
  1. **Tier 1 (pdfplumber):** Executes in ~20 ms for vector PDFs, preserving exact character bounding boxes.
  2. **Tier 2 (Tesseract with OpenCV):** Used for scanned PDFs/images; applies Otsu thresholding, deskewing, and contrast normalization.
  3. **Tier 3 (Multimodal Gemini Vision):** Invoked only if Tier 1 and 2 yield low confidence (<0.60) or fewer than 2 biomarkers.
- **Consequences:**
  - *Positive:* 100% extraction accuracy across both digital PDFs and photographed phone images; 90%+ of reports process on Tier 1 in <30 ms with zero external API cost.
  - *Negative:* Requires local system dependencies (`ghostscript`, `libgl1`) managed via Dockerfile.

---

### ADR-006: Fine-Grained Claim-Level Citation Attribution vs. Document References

- **Status:** Accepted
- **Context:** Broad document-level citations ("Source: MedlinePlus") fail clinical verification because users cannot tell which specific sentence was derived from which medical guideline or which report value.
- **Decision:** Adopt an atomic attribution schema:
  $$\{\text{claim}: \text{"Fasting blood sugar of 142 mg/dL is above normal"}, \text{source\_ids}: [\text{"rep:p1:l14"}, \text{"kb:MEDLINE-GLUCOSE"}]\}$$
  Enforced by two automated checks:
  1. *Programmatic:* Source IDs must exist in the report or KB manifest.
  2. *Semantic:* Extracted numeric tokens must match the referenced source verbatim.
- **Consequences:**
  - *Positive:* 100.0% citation accuracy across 63 eval cases; powers interactive UI citations where clicking an anchor reveals the exact source excerpt and bounding box.
  - *Negative:* Slightly larger LLM prompt and output payload.
