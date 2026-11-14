"""Layer 1 Input Guard: blocks adversarial diagnosis and prescription requests."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional

from pydantic import BaseModel, Field

from src.config import get_config
from src.explainer.prompts import build_classifier_prompt

logger = logging.getLogger("input_guard")


class GuardrailResult(BaseModel):
    """Result of an input guardrail security inspection."""
    __test__ = False
    blocked: bool = False
    violation_category: Optional[str] = None
    matched_pattern: Optional[str] = None
    safe_response_en: str = ""
    safe_response_hi: str = ""


class InputGuard:
    """Inspects and filters user inputs attempting to solicit medical diagnoses or prescriptions."""

    def __init__(self):
        self.config = get_config().guardrails.input_guard
        self.disclaimer_config = get_config().guardrails.disclaimer

        # Precompile pattern blocklist regexes
        self.en_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.pattern_blocklist.get("en", [])
        ]
        self.hi_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.pattern_blocklist.get("hi", [])
        ]

    def _matches_keywords(self, text: str, keywords: List[str]) -> Optional[str]:
        """Check if any keyword appears as a distinct word in text."""
        text_lower = text.lower()
        for kw in keywords:
            # Word boundary check for english/ascii words
            if re.search(rf"\b{re.escape(kw.lower())}\b", text_lower):
                return kw
            # Direct inclusion check for non-ascii / devanagari scripts
            if any(ord(c) > 127 for c in kw) and kw in text:
                return kw
        return None

    def _matches_patterns(self, text: str, patterns: List[re.Pattern]) -> Optional[str]:
        """Check if any compiled regex pattern matches the text."""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def check(self, user_message: str) -> GuardrailResult:
        """Evaluate a user prompt against all Layer 1 safety criteria."""
        if not user_message or not user_message.strip():
            return GuardrailResult(blocked=False)

        clean_msg = user_message.strip()

        # 1. Check Regex Patterns (highest fidelity, e.g. 'should I take', 'do I have')
        matched_pattern = self._matches_patterns(clean_msg, self.en_patterns)
        if matched_pattern:
            return GuardrailResult(
                blocked=True,
                violation_category="diagnosis_or_medication_query",
                matched_pattern=matched_pattern,
                safe_response_en=self.config.safe_refusal.get("en", "Please consult your doctor."),
                safe_response_hi=self.config.safe_refusal.get("hi", "कृपया अपने डॉक्टर से परामर्श करें।"),
            )

        matched_hi_pattern = self._matches_patterns(clean_msg, self.hi_patterns)
        if matched_hi_pattern:
            return GuardrailResult(
                blocked=True,
                violation_category="hindi_diagnosis_or_medication_query",
                matched_pattern=matched_hi_pattern,
                safe_response_en=self.config.safe_refusal.get("en", "Please consult your doctor."),
                safe_response_hi=self.config.safe_refusal.get("hi", "कृपया अपने डॉक्टर से परामर्श करें।"),
            )

        # 2. Check Keyword Blocklists
        matched_kw_en = self._matches_keywords(
            clean_msg, self.config.keyword_blocklist.get("en", [])
        )
        if matched_kw_en:
            return GuardrailResult(
                blocked=True,
                violation_category="restricted_keyword_en",
                matched_pattern=matched_kw_en,
                safe_response_en=self.config.safe_refusal.get("en", "Please consult your doctor."),
                safe_response_hi=self.config.safe_refusal.get("hi", "कृपया अपने डॉक्टर से परामर्श करें।"),
            )

        matched_kw_hi = self._matches_keywords(
            clean_msg, self.config.keyword_blocklist.get("hi", [])
        )
        if matched_kw_hi:
            return GuardrailResult(
                blocked=True,
                violation_category="restricted_keyword_hi",
                matched_pattern=matched_kw_hi,
                safe_response_en=self.config.safe_refusal.get("en", "Please consult your doctor."),
                safe_response_hi=self.config.safe_refusal.get("hi", "कृपया अपने डॉक्टर से परामर्श करें।"),
            )

        # 3. Optional LLM Safety Classifier for subtle adversarial edge cases
        api_key = os.environ.get("GEMINI_API_KEY") or get_config().gemini_api_key
        if self.config.use_llm_classifier and api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                prompt = build_classifier_prompt(clean_msg)

                response = client.models.generate_content(
                    model=self.config.classifier_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    raw_resp = response.text.strip()
                    if raw_resp.startswith("```"):
                        raw_resp = re.sub(r"^```(?:json)?\s*", "", raw_resp)
                        raw_resp = re.sub(r"\s*```$", "", raw_resp)
                    match = re.search(r"\{[\s\S]*\}", raw_resp)
                    if match:
                        raw_resp = match.group(0)
                    parsed = json.loads(raw_resp)
                    if not parsed.get("is_safe", True):
                        return GuardrailResult(
                            blocked=True,
                            violation_category=parsed.get("violation_category", "unsafe_clinical_query"),
                            matched_pattern=parsed.get("reason", "Soliciting clinical advice"),
                            safe_response_en=self.config.safe_refusal.get("en", "Please consult your doctor."),
                            safe_response_hi=self.config.safe_refusal.get("hi", "कृपया अपने डॉक्टर से परामर्श करें।"),
                        )
            except Exception as e:
                logger.warning(f"LLM safety classifier call failed ({e}); falling back to heuristic passes.")

        return GuardrailResult(blocked=False)
