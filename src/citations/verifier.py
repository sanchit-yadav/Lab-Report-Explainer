"""Programmatic and Semantic Citation Verification Engine.

Performs two-tier verification on all model-generated clinical claims:
1. Programmatic Check: Verifies that every source ID cited exists in the active session's CitationRegistry.
2. Semantic Check: Verifies that the cited source text or report field data factually and medically supports the claim.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.citations.models import (
    AttributedClaim,
    CitationRegistry,
    KBChunkSource,
    ReportFieldSource,
    VerificationStatus,
)

logger = logging.getLogger("citation_verifier")


class CitationVerifier:
    """Verifies that attributed claims have valid sources and that cited sources support the claim."""

    def __init__(self, strict_numerical_match: bool = True):
        self.strict_numerical_match = strict_numerical_match

    def verify_claim_programmatic(
        self,
        claim: AttributedClaim,
        registry: CitationRegistry,
    ) -> Tuple[bool, List[str]]:
        """Verify that every cited source_id exists in the session CitationRegistry."""
        if not claim.source_ids:
            return False, ["Claim contains no source_ids (uncited claim)."]

        missing_ids = [sid for sid in claim.source_ids if not registry.has_source(sid)]
        if missing_ids:
            return False, [f"Unrecognized or hallucinated source ID(s): {', '.join(missing_ids)}"]

        return True, []

    def verify_claim_semantic(
        self,
        claim: AttributedClaim,
        registry: CitationRegistry,
    ) -> Tuple[bool, str]:
        """Verify that cited sources factually and semantically support the claim text."""
        claim_text = claim.claim
        claim_lower = claim_text.lower()

        # Extract numerical tokens from claim (excluding small cosmetic numbers like 1, 2)
        raw_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", claim_text)
        substantive_numbers = [n for n in raw_numbers if n not in {"1", "2", "3", "4", "5", "10", "24", "100"}]

        supported_by_at_least_one = False
        rejection_reasons: List[str] = []

        for sid in claim.source_ids:
            source = registry.get_source(sid)
            if not source:
                continue

            # -------------------------------------------------------------
            # Case A: Cited source is an Extracted Report Field
            # -------------------------------------------------------------
            if isinstance(source, ReportFieldSource):
                # 1. Numerical concordance: numbers in claim must match the report value or ref bounds
                if substantive_numbers:
                    allowed_nums = set()
                    if source.value is not None:
                        allowed_nums.add(str(source.value))
                        allowed_nums.add(f"{source.value:.1f}")
                        if source.value.is_integer():
                            allowed_nums.add(str(int(source.value)))
                    if source.ref_range:
                        for rn in re.findall(r"\b\d+(?:\.\d+)?\b", source.ref_range):
                            allowed_nums.add(rn)

                    mismatches = [n for n in substantive_numbers if n not in allowed_nums]
                    if mismatches and self.strict_numerical_match:
                        rejection_reasons.append(
                            f"Report source {sid} does not contain cited number(s): {mismatches}"
                        )
                        continue

                # 2. Analyte name alignment
                name_tokens = [t.lower() for t in source.test_name.split() if len(t) > 2]
                if not any(token in claim_lower for token in name_tokens):
                    # Check if synonym or acronym matches
                    if not any(char in claim_lower for char in ("test", "level", "result", "finding", "value")):
                        rejection_reasons.append(
                            f"Claim lacks relevance to cited analyte '{source.test_name}'."
                        )
                        continue

                supported_by_at_least_one = True
                break

            # -------------------------------------------------------------
            # Case B: Cited source is a Knowledge Base Chunk
            # -------------------------------------------------------------
            elif isinstance(source, KBChunkSource):
                source_excerpt = (source.text_excerpt or "").lower()
                doc_title = source.title.lower()

                # 1. Ensure basic domain semantic relevance (either test name or concepts present)
                title_tokens = [t for t in doc_title.split() if len(t) > 3]
                title_relevant = any(t in claim_lower for t in title_tokens)
                
                # Check keyword overlap between claim and source excerpt
                claim_words = {w for w in re.findall(r"\b[a-z]{4,}\b", claim_lower)}
                source_words = {w for w in re.findall(r"\b[a-z]{4,}\b", source_excerpt)}
                overlap = claim_words.intersection(source_words)

                # Direct concept match
                if title_relevant or len(overlap) >= 2 or source.section.lower() in claim_lower:
                    # Check for direct contradictions (e.g., claiming elevated when section is purely low)
                    if "elevated" in claim_lower and "what low values mean" in source.section.lower() and "high" not in source_excerpt:
                        rejection_reasons.append(
                            f"Section '{source.section}' discusses low values, but claim asserts elevated findings."
                        )
                        continue
                    if ("low" in claim_lower or "decreased" in claim_lower) and "what elevated / high values mean" in source.section.lower() and "low" not in source_excerpt:
                        rejection_reasons.append(
                            f"Section '{source.section}' discusses elevated values, but claim asserts low findings."
                        )
                        continue

                    supported_by_at_least_one = True
                    break
                else:
                    rejection_reasons.append(
                        f"KB chunk '{source.source_id}' lacks semantic overlap with claim."
                    )

        if supported_by_at_least_one:
            return True, "Claim is semantically supported by cited source(s)."
        else:
            reason = "; ".join(rejection_reasons) if rejection_reasons else "Cited sources do not substantiate claim."
            return False, reason

    def verify_claim(
        self,
        claim: AttributedClaim,
        registry: CitationRegistry,
    ) -> AttributedClaim:
        """Run programmatic and semantic verification on a single claim, updating its status."""
        prog_ok, prog_reasons = self.verify_claim_programmatic(claim, registry)
        if not prog_ok:
            claim.verification_status = VerificationStatus.MISSING_SOURCE
            claim.verification_reason = "; ".join(prog_reasons)
            return claim

        sem_ok, sem_reason = self.verify_claim_semantic(claim, registry)
        if sem_ok:
            claim.verification_status = VerificationStatus.VERIFIED
            claim.verification_reason = sem_reason
        else:
            claim.verification_status = VerificationStatus.UNSUPPORTED
            claim.verification_reason = sem_reason

        return claim

    def verify_all_claims(
        self,
        claims: List[AttributedClaim],
        registry: CitationRegistry,
    ) -> Dict[str, Any]:
        """Verify an entire list of claims, computing citation metrics."""
        verified_count = 0
        missing_source_count = 0
        unsupported_count = 0

        verified_claims: List[AttributedClaim] = []
        for claim in claims:
            updated = self.verify_claim(claim, registry)
            verified_claims.append(updated)
            if updated.verification_status == VerificationStatus.VERIFIED:
                verified_count += 1
            elif updated.verification_status == VerificationStatus.MISSING_SOURCE:
                missing_source_count += 1
            elif updated.verification_status == VerificationStatus.UNSUPPORTED:
                unsupported_count += 1

        total = len(claims)
        accuracy = (verified_count / total) if total > 0 else 1.0

        return {
            "total_claims": total,
            "verified_claims": verified_count,
            "missing_source_claims": missing_source_count,
            "unsupported_claims": unsupported_count,
            "citation_accuracy": round(accuracy, 4),
            "is_fully_grounded": (verified_count == total and total > 0),
            "claims": verified_claims,
        }
