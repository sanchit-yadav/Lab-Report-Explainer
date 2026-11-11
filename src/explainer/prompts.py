"""Prompt construction and management for clinical explanations and evaluation."""

from __future__ import annotations

from typing import List, Optional

from src.config import get_config
from src.extraction.schema import TestResult


def get_system_prompt() -> str:
    """Load the immutable clinical educator system prompt."""
    return get_config().prompts.system_prompt


def build_explanation_prompt(
    test: TestResult,
    context_chunks: List[str],
    source_urls: List[str],
) -> str:
    """Format the explanation generation prompt template."""
    config = get_config()
    template = config.prompts.explainer_prompt

    context_str = "\n\n---\n\n".join(context_chunks) if context_chunks else "No specific guideline text available."
    sources_str = "\n".join(f"- {url}" for url in source_urls) if source_urls else "General clinical knowledge."

    return template.format(
        test_name=test.test_name,
        value=test.value if test.value is not None else test.raw_value,
        unit=test.unit or "",
        ref_raw=test.ref_raw or f"{test.ref_low} - {test.ref_high}",
        flag=test.flag.value.upper(),
        context=context_str,
        sources=sources_str,
    )


def build_classifier_prompt(user_message: str) -> str:
    """Format the safety classifier prompt for user questions."""
    template = get_config().prompts.guardrail_classifier
    return template.format(user_message=user_message)


def build_eval_judge_prompt(
    test_name: str,
    value: str,
    unit: str,
    flag: str,
    context: str,
    explanation: str,
) -> str:
    """Format the evaluation judge prompt for quality scoring."""
    template = get_config().prompts.eval_judge_prompt
    return template.format(
        test_name=test_name,
        value=value,
        unit=unit,
        flag=flag,
        context=context,
        explanation=explanation,
    )
