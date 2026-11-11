"""Layer 3 Output Guard: sanitizes LLM-generated explanations against medical advice."""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from src.config import get_config
from src.explainer.schema import TestExplanation

logger = logging.getLogger("output_guard")


class OutputGuard:
    """Scans and redacts unauthorized drug recommendations, diagnostic statements, and dosages."""

    def __init__(self):
        self.config = get_config().guardrails.output_guard
        self.drug_names = get_config().prompts.drug_names
        self.disclaimer_en = get_config().guardrails.disclaimer.get("en", "")
        self.disclaimer_hi = get_config().guardrails.disclaimer.get("hi", "")

        # Compile drug name regex pattern with word boundaries
        if self.drug_names:
            escaped_drugs = [re.escape(d) for d in self.drug_names if len(d) > 2]
            self.drug_pattern = re.compile(
                rf"\b(?:{'|'.join(escaped_drugs)})\b",
                re.IGNORECASE,
            )
        else:
            self.drug_pattern = None

        # Compile unsafe diagnostic regex patterns
        self.unsafe_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.unsafe_patterns
        ]

    def sanitize_text(self, text: str, lang: str = "en") -> Tuple[str, int]:
        """Scan a text block and replace unsafe clinical assertions.

        Returns (sanitized_text, violation_count).
        """
        if not text:
            return "", 0

        replacement = self.config.replacement_text.get(
            lang, "Please discuss this specific result with your doctor for guidance."
        )
        violations = 0

        # 1. Check & sanitize drug names
        if self.drug_pattern and self.drug_pattern.search(text):
            violations += len(self.drug_pattern.findall(text))
            text = self.drug_pattern.sub("[Medication - Consult Doctor]", text)

        # 2. Check & sanitize unsafe diagnostic or dosage statements
        for pattern in self.unsafe_patterns:
            matches = pattern.findall(text)
            if matches:
                violations += len(matches)
                text = pattern.sub(replacement, text)

        return text, violations

    def check(self, explanation: TestExplanation) -> TestExplanation:
        """Inspect and sanitize a TestExplanation instance."""
        sanitized_en, v_en = self.sanitize_text(explanation.explanation_en, lang="en")
        sanitized_hi, v_hi = self.sanitize_text(explanation.explanation_hi, lang="hi")

        if v_en > 0:
            logger.warning(f"Output guard redacted {v_en} unsafe assertion(s) in English explanation for '{explanation.test_name}'.")
        if v_hi > 0:
            logger.warning(f"Output guard redacted {v_hi} unsafe assertion(s) in Hindi explanation for '{explanation.test_name}'.")

        explanation.explanation_en = sanitized_en
        explanation.explanation_hi = sanitized_hi

        # Ensure disclaimer is always present
        if not explanation.disclaimer:
            explanation.disclaimer = self.disclaimer_en

        return explanation
