"""Citation Formatter and UI Presentation Renderer.

Transforms structured {claim, source_ids[]} and CitationRegistry instances into:
1. Inline markdown text with numeric superscript anchors: e.g. "Your glucose is 110 mg/dL [1]..."
2. Markdown Bibliography / References list with clickable links and physical report page/line provenance.
3. Interactive UI component payloads (JSON) for modern frontend hovercards, badges, and source pills.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.citations.models import (
    AttributedClaim,
    CitationRegistry,
    KBChunkSource,
    ReportFieldSource,
    SourceKind,
    VerificationStatus,
)


class CitationFormatter:
    """Formats structured attributed claims for UI and PDF rendering."""

    @staticmethod
    def format_inline_with_bibliography(
        claims: List[AttributedClaim],
        registry: CitationRegistry,
        include_unverified_warning: bool = True,
    ) -> Tuple[str, str]:
        """Format a list of claims into an inline narrative plus an enumerated bibliography.

        Returns:
            Tuple[str, str]: (inline_annotated_text, markdown_bibliography)
        """
        source_id_to_num: Dict[str, int] = {}
        ordered_sources: List[Tuple[str, Any]] = []

        # 1. Map and deduplicate source identifiers in order of appearance
        for claim in claims:
            for sid in claim.source_ids:
                if sid not in source_id_to_num:
                    num = len(source_id_to_num) + 1
                    source_id_to_num[sid] = num
                    ordered_sources.append((sid, registry.get_source(sid)))

        # 2. Build annotated narrative
        narrative_parts: List[str] = []
        for claim in claims:
            anchors = [f"[{source_id_to_num[sid]}]" for sid in claim.source_ids if sid in source_id_to_num]
            anchor_str = f" {''.join(anchors)}" if anchors else ""

            if claim.verification_status == VerificationStatus.UNSUPPORTED and include_unverified_warning:
                narrative_parts.append(f"{claim.claim}{anchor_str} *(⚠️ unverified citation)*")
            elif claim.verification_status == VerificationStatus.MISSING_SOURCE and include_unverified_warning:
                narrative_parts.append(f"{claim.claim}{anchor_str} *(⚠️ missing source)*")
            else:
                narrative_parts.append(f"{claim.claim}{anchor_str}")

        annotated_text = " ".join(narrative_parts)

        # 3. Build enumerated bibliography
        bib_lines: List[str] = ["### References & Clinical Grounding Sources\n"]
        for sid, src in ordered_sources:
            num = source_id_to_num[sid]
            if src is None:
                bib_lines.append(f"{num}. **[Unrecognized Source ID]**: `{sid}`")
            elif isinstance(src, ReportFieldSource):
                val_display = f"{src.value} {src.unit or ''}".strip() if src.value is not None else "Observed"
                bib_lines.append(
                    f"{num}. **Patient Report Field**: {src.test_name} (Value: `{val_display}`, Range: `{src.ref_range or 'N/A'}`) — *Page {src.source_page}, Location: {src.source_location}*"
                )
            elif isinstance(src, KBChunkSource):
                bib_lines.append(
                    f"{num}. **{src.publisher}**: *[{src.title} - '{src.section}']({src.url})* (Version: `{src.version}`, Reviewed: `{src.review_date}`)"
                )
            else:
                bib_lines.append(f"{num}. **Source**: `{sid}`")

        bibliography = "\n".join(bib_lines)
        return annotated_text, bibliography

    @staticmethod
    def format_ui_payload(
        claims: List[AttributedClaim],
        registry: CitationRegistry,
    ) -> Dict[str, Any]:
        """Generate structured JSON payload for React/Vue UI interactive components."""
        claim_cards: List[Dict[str, Any]] = []
        source_index: Dict[str, Dict[str, Any]] = {}

        for claim in claims:
            attached_citations: List[Dict[str, Any]] = []
            for sid in claim.source_ids:
                src = registry.get_source(sid)
                if src:
                    if isinstance(src, ReportFieldSource):
                        source_meta = {
                            "source_id": src.source_id,
                            "type": "report_field",
                            "badge_label": f"Report p.{src.source_page}",
                            "title": src.test_name,
                            "page": src.source_page,
                            "location": src.source_location,
                            "value": src.value,
                            "unit": src.unit,
                            "ref_range": src.ref_range,
                            "flag": src.flag,
                        }
                    elif isinstance(src, KBChunkSource):
                        source_meta = {
                            "source_id": src.source_id,
                            "type": "kb_guideline",
                            "badge_label": "Clinical Guideline",
                            "title": src.title,
                            "section": src.section,
                            "url": src.url,
                            "version": src.version,
                            "review_date": src.review_date,
                            "publisher": src.publisher,
                            "excerpt": src.text_excerpt[:160] if src.text_excerpt else None,
                        }
                    else:
                        source_meta = {"source_id": sid, "type": "unknown"}
                    attached_citations.append(source_meta)
                    source_index[sid] = source_meta

            claim_cards.append({
                "claim_id": claim.claim_id,
                "claim_text": claim.claim,
                "verification_status": claim.verification_status.value,
                "verification_reason": claim.verification_reason,
                "citations": attached_citations,
            })

        return {
            "claims": claim_cards,
            "total_claims": len(claims),
            "sources": source_index,
        }
