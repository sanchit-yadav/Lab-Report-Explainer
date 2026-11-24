"""Data models for structured citations, attributed claims, and source registry.

Enforces schema: {claim, source_ids[]} where sources are:
- Report fields (page + line/bbox coordinates, extracted value, unit)
- Knowledge-base chunks (doc_id, title, section, URL, version, review date)
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    """Categorical classification of citation sources."""

    REPORT_FIELD = "report_field"
    KB_CHUNK = "kb_chunk"


class ReportFieldSource(BaseModel):
    """Grounding source anchored in the patient's physical uploaded report."""

    source_id: str = Field(description="Unique source ID, e.g. 'report:glucose:p1:l4'")
    kind: SourceKind = Field(default=SourceKind.REPORT_FIELD)
    test_name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    ref_range: Optional[str] = None
    flag: Optional[str] = None
    source_page: int = 1
    source_location: str = Field(
        default="line_1", description="Line identifier or bbox coordinates"
    )

    def to_citation_label(self) -> str:
        """Human-readable citation label for UI/Doctor Brief."""
        val_str = (
            f"{self.value} {self.unit or ''}".strip() if self.value is not None else "observed"
        )
        return f"Lab Report: {self.test_name} ({val_str}) [Page {self.source_page}, {self.source_location}]"


class KBChunkSource(BaseModel):
    """Grounding source anchored in curated clinical reference knowledge base."""

    source_id: str = Field(
        description="Unique source ID, e.g. 'kb:medlineplus:fasting_blood_glucose:sec1'"
    )
    kind: SourceKind = Field(default=SourceKind.KB_CHUNK)
    doc_id: str
    title: str
    section: str = "General Guidelines"
    url: str
    version: str = "2024.1"
    review_date: str = "2024-05-15"
    publisher: str = "MedlinePlus (U.S. National Library of Medicine)"
    text_excerpt: Optional[str] = None

    def to_citation_label(self) -> str:
        """Human-readable citation label for UI/Doctor Brief."""
        return f"{self.publisher}: {self.title} - '{self.section}' (v{self.version})"


class VerificationStatus(str, Enum):
    """Clinical verification status of an individual attributed claim."""

    VERIFIED = "VERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    MISSING_SOURCE = "MISSING_SOURCE"
    PENDING = "PENDING"


class AttributedClaim(BaseModel):
    """Structured clinical claim anchored to explicit source identifiers."""

    claim_id: str = Field(default="", description="Unique claim identifier, e.g. 'claim_1'")
    claim: str = Field(description="Specific factual or educational clinical statement")
    source_ids: List[str] = Field(
        default_factory=list,
        description="List of cited source IDs (report field or KB chunk identifiers)",
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.PENDING,
        description="Whether the claim was verified programmatically and semantically",
    )
    verification_reason: Optional[str] = Field(
        default=None, description="Diagnostic details from the citation verification engine"
    )


class CitationRegistry(BaseModel):
    """Container holding all valid grounding sources for a given report session."""

    report_sources: Dict[str, ReportFieldSource] = Field(default_factory=dict)
    kb_sources: Dict[str, KBChunkSource] = Field(default_factory=dict)

    def register_report_field(
        self,
        test_name: str,
        value: Optional[float],
        unit: Optional[str],
        ref_range: Optional[str],
        flag: Optional[str],
        source_page: int = 1,
        source_location: str = "line_1",
    ) -> ReportFieldSource:
        """Register an extracted report field and return its unique source object."""
        slug = test_name.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        loc_slug = source_location.lower().replace(" ", "_").replace(":", "_")
        source_id = f"report:{slug}:p{source_page}:{loc_slug}"
        source = ReportFieldSource(
            source_id=source_id,
            test_name=test_name,
            value=value,
            unit=unit,
            ref_range=ref_range,
            flag=flag,
            source_page=source_page,
            source_location=source_location,
        )
        self.report_sources[source_id] = source
        return source

    def register_kb_chunk(
        self,
        doc_id: str,
        title: str,
        section: str,
        url: str,
        text_excerpt: str,
        version: str = "2024.1",
        review_date: str = "2024-05-15",
        publisher: str = "MedlinePlus (U.S. National Library of Medicine)",
    ) -> KBChunkSource:
        """Register a retrieved knowledge base chunk and return its unique source object."""
        doc_slug = doc_id.lower().replace(" ", "_").replace("-", "_")
        sec_slug = section.lower().replace(" ", "_")[:24]
        source_id = f"kb:{doc_slug}:{sec_slug}"
        source = KBChunkSource(
            source_id=source_id,
            doc_id=doc_id,
            title=title,
            section=section,
            url=url,
            version=version,
            review_date=review_date,
            publisher=publisher,
            text_excerpt=text_excerpt,
        )
        self.kb_sources[source_id] = source
        return source

    def has_source(self, source_id: str) -> bool:
        """Programmatic check: verify if a source ID exists in active registry."""
        return (source_id in self.report_sources) or (source_id in self.kb_sources)

    def get_source(self, source_id: str) -> Optional[Union[ReportFieldSource, KBChunkSource]]:
        """Retrieve source object by ID."""
        return self.report_sources.get(source_id) or self.kb_sources.get(source_id)

    @property
    def all_source_ids(self) -> List[str]:
        """Return all valid registered source IDs."""
        return list(self.report_sources.keys()) + list(self.kb_sources.keys())
