"""Configuration management for AI Lab Report Explainer.

Loads, validates, and serves all configuration files (YAML) and environment
variables using Pydantic Settings. No hardcoded thresholds, prompts, or model names.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project Root Directory Resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"


def _load_yaml(file_path: Path) -> Dict[str, Any]:
    """Helper to safely load a YAML configuration file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_text_file(file_path: Path) -> str:
    """Helper to load a text/prompt file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Required prompt/text file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ==============================================================================
# 1. App Configuration Models (app_config.yaml)
# ==============================================================================

class ModelsConfig(BaseModel):
    explanation_llm: str = Field(default="gemini-3.1-flash-lite")
    explanation_thinking_level: str = Field(default="low")
    vision_fallback: str = Field(default="gemini-3.5-flash")
    vision_media_resolution: str = Field(default="medium")
    guardrail_classifier: str = Field(default="gemini-3.1-flash-lite")
    eval_judge: str = Field(default="gemini-3.5-flash")
    eval_thinking_level: str = Field(default="high")


class GenerationConfig(BaseModel):
    temperature: float = Field(default=0.2)
    max_output_tokens: int = Field(default=2048)


class LanguagesConfig(BaseModel):
    supported: List[str] = Field(default_factory=lambda: ["en", "hi"])
    default: str = Field(default="en")


class TracingConfig(BaseModel):
    enabled: bool = Field(default=True)
    provider: str = Field(default="langfuse")


# ==============================================================================
# 2. Extraction Configuration Models (extraction_config.yaml)
# ==============================================================================

class ExtractionTier(BaseModel):
    name: str
    enabled: bool = True
    priority: int
    method: Optional[str] = None
    model: Optional[str] = None


class HeaderPatterns(BaseModel):
    test_name: List[str] = Field(default_factory=list)
    value: List[str] = Field(default_factory=list)
    unit: List[str] = Field(default_factory=list)
    ref_range: List[str] = Field(default_factory=list)


class FlaggingConfig(BaseModel):
    critical_multiplier: float = Field(default=2.0)
    non_numeric_map: Dict[str, str] = Field(default_factory=dict)


class ReportTypeConfig(BaseModel):
    extractor: str
    flagger: str
    rag_collection: str


class ExtractionConfig(BaseModel):
    tiers: List[ExtractionTier] = Field(default_factory=list)
    header_patterns: HeaderPatterns = Field(default_factory=HeaderPatterns)
    flagging: FlaggingConfig = Field(default_factory=FlaggingConfig)
    report_types: Dict[str, ReportTypeConfig] = Field(default_factory=dict)


# ==============================================================================
# 3. RAG Configuration Models (rag_config.yaml)
# ==============================================================================

class EmbeddingsConfig(BaseModel):
    model: str = Field(default="gemini-embedding-2")
    dimensions: int = Field(default=768)
    task_type: str = Field(default="RETRIEVAL_QUERY")
    doc_task_type: str = Field(default="RETRIEVAL_DOCUMENT")


class VectorStoreConfig(BaseModel):
    provider: str = Field(default="chromadb")
    persist_directory: str = Field(default="./chroma_db")
    collection_name: str = Field(default="lab_tests")


class RetrievalConfig(BaseModel):
    top_k: int = Field(default=10)
    similarity_threshold: float = Field(default=0.65)


class RerankerConfig(BaseModel):
    enabled: bool = Field(default=True)
    model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    top_n: int = Field(default=3)


class ChunkingConfig(BaseModel):
    strategy: str = Field(default="document_level")


class RAGConfig(BaseModel):
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)


# ==============================================================================
# 4. Guardrails Configuration Models (guardrails_config.yaml)
# ==============================================================================

class InputGuardConfig(BaseModel):
    enabled: bool = True
    use_llm_classifier: bool = True
    classifier_model: str = "gemini-3.1-flash-lite"
    keyword_blocklist: Dict[str, List[str]] = Field(default_factory=dict)
    pattern_blocklist: Dict[str, List[str]] = Field(default_factory=dict)
    safe_refusal: Dict[str, str] = Field(default_factory=dict)


class OutputGuardConfig(BaseModel):
    enabled: bool = True
    unsafe_patterns: List[str] = Field(default_factory=list)
    drug_list_file: str = "config/drug_names.txt"
    replacement_text: Dict[str, str] = Field(default_factory=dict)


class GuardrailsConfig(BaseModel):
    input_guard: InputGuardConfig = Field(default_factory=InputGuardConfig)
    output_guard: OutputGuardConfig = Field(default_factory=OutputGuardConfig)
    disclaimer: Dict[str, str] = Field(default_factory=dict)


# ==============================================================================
# 5. Evaluation Configuration Models (eval_config.yaml)
# ==============================================================================

class ExtractionEvalTargets(BaseModel):
    f1_min: float = 0.90
    test_name_precision_min: float = 0.95
    value_accuracy_min: float = 0.95
    unit_accuracy_min: float = 0.90
    range_accuracy_min: float = 0.85


class FlaggingEvalTargets(BaseModel):
    accuracy_required: float = 1.00


class RetrievalEvalTargets(BaseModel):
    recall_at_3_min: float = 0.93
    recall_at_1_min: float = 0.80
    mrr_min: float = 0.90
    reranker_lift_min: float = 0.05
    query_latency_p95_ms: int = 200


class GenerationEvalTargets(BaseModel):
    faithfulness_min: float = 4.0
    completeness_min: float = 4.0
    clarity_min: float = 4.0
    citation_compliance: float = 1.00
    doctor_referral_compliance: float = 1.00
    hindi_naturalness_min: float = 3.5


class GuardrailsEvalTargets(BaseModel):
    block_rate_min: float = 0.95
    false_positive_max: float = 0.05


class PerformanceEvalTargets(BaseModel):
    latency_p50_max_sec: float = 10.0
    cost_per_report_max_usd: float = 0.01


class EvalTargets(BaseModel):
    extraction: ExtractionEvalTargets = Field(default_factory=ExtractionEvalTargets)
    flagging: FlaggingEvalTargets = Field(default_factory=FlaggingEvalTargets)
    retrieval: RetrievalEvalTargets = Field(default_factory=RetrievalEvalTargets)
    generation: GenerationEvalTargets = Field(default_factory=GenerationEvalTargets)
    guardrails: GuardrailsEvalTargets = Field(default_factory=GuardrailsEvalTargets)
    performance: PerformanceEvalTargets = Field(default_factory=PerformanceEvalTargets)


class EvalConfig(BaseModel):
    targets: EvalTargets = Field(default_factory=EvalTargets)


# ==============================================================================
# 6. Prompts & Knowledge Assets
# ==============================================================================

class Prompts(BaseModel):
    system_prompt: str
    explainer_prompt: str
    guardrail_classifier: str
    eval_judge_prompt: str
    drug_names: List[str] = Field(default_factory=list)


# ==============================================================================
# 7. Unified Master Settings
# ==============================================================================

class Settings(BaseSettings):
    """Unified application settings combining YAML files and environment variables."""

    # Environment variables (secrets & endpoints)
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # Domain Configurations loaded from YAML
    models: ModelsConfig
    generation: GenerationConfig
    languages: LanguagesConfig
    tracing: TracingConfig
    extraction: ExtractionConfig
    rag: RAGConfig
    guardrails: GuardrailsConfig
    eval: EvalConfig
    prompts: Prompts

    # Paths
    project_root: Path = PROJECT_ROOT
    config_dir: Path = CONFIG_DIR

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@functools.lru_cache(maxsize=1)
def get_config() -> Settings:
    """Load and return the singleton Settings object."""
    app_data = _load_yaml(CONFIG_DIR / "app_config.yaml")
    extraction_data = _load_yaml(CONFIG_DIR / "extraction_config.yaml")
    rag_data = _load_yaml(CONFIG_DIR / "rag_config.yaml")
    guardrails_data = _load_yaml(CONFIG_DIR / "guardrails_config.yaml")
    eval_data = _load_yaml(CONFIG_DIR / "eval_config.yaml")

    # Load prompts
    system_prompt = _load_text_file(PROMPTS_DIR / "system_prompt.txt")
    explainer_prompt = _load_text_file(PROMPTS_DIR / "explainer_prompt.txt")
    guardrail_classifier = _load_text_file(PROMPTS_DIR / "guardrail_classifier.txt")
    eval_judge_prompt = _load_text_file(PROMPTS_DIR / "eval_judge_prompt.txt")

    # Load drug names
    drug_file = PROJECT_ROOT / guardrails_data.get("output_guard", {}).get(
        "drug_list_file", "config/drug_names.txt"
    )
    drug_names: List[str] = []
    if drug_file.exists():
        with open(drug_file, "r", encoding="utf-8") as f:
            drug_names = [
                line.strip().lower()
                for line in f
                if line.strip() and not line.startswith("#")
            ]

    prompts = Prompts(
        system_prompt=system_prompt,
        explainer_prompt=explainer_prompt,
        guardrail_classifier=guardrail_classifier,
        eval_judge_prompt=eval_judge_prompt,
        drug_names=drug_names,
    )

    return Settings(
        models=ModelsConfig(**app_data.get("models", {})),
        generation=GenerationConfig(**app_data.get("generation", {})),
        languages=LanguagesConfig(**app_data.get("languages", {})),
        tracing=TracingConfig(**app_data.get("tracing", {})),
        extraction=ExtractionConfig(**extraction_data),
        rag=RAGConfig(**rag_data),
        guardrails=GuardrailsConfig(**guardrails_data),
        eval=EvalConfig(**eval_data),
        prompts=prompts,
    )
