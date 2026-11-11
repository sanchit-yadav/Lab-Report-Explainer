"""Unit tests for configuration loader and schema validation."""

import pytest
from src.config import get_config


def test_get_config_loads_successfully():
    """Verify that get_config executes and returns a valid Settings instance."""
    config = get_config()
    assert config is not None
    assert config.project_root.exists()
    assert config.config_dir.exists()


def test_model_configurations():
    """Verify that models match the locked Gemini 3 architecture."""
    config = get_config()
    assert config.models.explanation_llm == "gemini-3.1-flash-lite"
    assert config.models.explanation_thinking_level == "low"
    assert config.models.vision_fallback == "gemini-3.5-flash"
    assert config.models.eval_judge == "gemini-3.5-flash"
    assert config.generation.temperature == 0.2
    assert "en" in config.languages.supported
    assert "hi" in config.languages.supported


def test_extraction_configuration():
    """Verify extraction tiers, header patterns, and deterministic flagging rules."""
    config = get_config()
    assert len(config.extraction.tiers) == 3
    tier_names = [tier.name for tier in config.extraction.tiers]
    assert tier_names == ["pdfplumber", "camelot", "vision"]

    # Header patterns
    patterns = config.extraction.header_patterns
    assert len(patterns.test_name) > 0
    assert len(patterns.value) > 0
    assert len(patterns.unit) > 0
    assert len(patterns.ref_range) > 0

    # Flagging rules
    assert config.extraction.flagging.critical_multiplier == 2.0
    assert config.extraction.flagging.non_numeric_map.get("positive") == "abnormal"
    assert config.extraction.flagging.non_numeric_map.get("non-reactive") == "normal"


def test_rag_configuration():
    """Verify RAG vector store, embedding model, and cross-encoder reranker settings."""
    config = get_config()
    assert config.rag.embeddings.model == "gemini-embedding-2"
    assert config.rag.embeddings.dimensions == 768
    assert config.rag.vector_store.provider == "chromadb"
    assert config.rag.retrieval.top_k == 10
    assert config.rag.reranker.enabled is True
    assert config.rag.reranker.top_n == 3
    assert "MiniLM" in config.rag.reranker.model


def test_guardrails_configuration():
    """Verify triple-layer guardrails, blocklists, and drug lists."""
    config = get_config()
    assert config.guardrails.input_guard.enabled is True
    assert "en" in config.guardrails.input_guard.keyword_blocklist
    assert "hi" in config.guardrails.input_guard.keyword_blocklist
    assert "prescribe" in config.guardrails.input_guard.keyword_blocklist["en"]
    assert "दवाई" in config.guardrails.input_guard.keyword_blocklist["hi"]

    # Unsafe output regex patterns
    assert len(config.guardrails.output_guard.unsafe_patterns) > 0
    assert len(config.prompts.drug_names) >= 20
    assert "metformin" in config.prompts.drug_names
    assert "atorvastatin" in config.prompts.drug_names

    # Refusals and disclaimers in EN and HI
    assert "en" in config.guardrails.disclaimer
    assert "hi" in config.guardrails.disclaimer


def test_prompt_templates():
    """Verify prompt templates are loaded and have expected placeholders."""
    config = get_config()
    assert len(config.prompts.system_prompt) > 50
    assert "{test_name}" in config.prompts.explainer_prompt
    assert "{context}" in config.prompts.explainer_prompt
    assert "{user_message}" in config.prompts.guardrail_classifier
    assert "{explanation}" in config.prompts.eval_judge_prompt


def test_eval_targets():
    """Verify evaluation targets are loaded."""
    config = get_config()
    assert config.eval.targets.extraction.f1_min == 0.90
    assert config.eval.targets.flagging.accuracy_required == 1.00
    assert config.eval.targets.retrieval.recall_at_3_min == 0.93
    assert config.eval.targets.guardrails.block_rate_min == 0.95
    assert config.eval.targets.guardrails.false_positive_max == 0.05
