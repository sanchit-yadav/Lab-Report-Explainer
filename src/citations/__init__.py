"""Citations & Attribution Module.

Provides structured claim extraction, source registration (report fields + KB chunks),
programmatic and semantic verification, and interactive UI rendering.
"""

from src.citations.models import (
    AttributedClaim,
    CitationRegistry,
    KBChunkSource,
    ReportFieldSource,
    SourceKind,
    VerificationStatus,
)
from src.citations.manifest import KBManifest, KBManifestManager, get_kb_manifest
from src.citations.verifier import CitationVerifier
from src.citations.formatter import CitationFormatter

__all__ = [
    "AttributedClaim",
    "CitationRegistry",
    "KBChunkSource",
    "ReportFieldSource",
    "SourceKind",
    "VerificationStatus",
    "KBManifest",
    "KBManifestManager",
    "get_kb_manifest",
    "CitationVerifier",
    "CitationFormatter",
]
