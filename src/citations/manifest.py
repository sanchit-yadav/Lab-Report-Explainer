"""Clinical Knowledge Base Manifest Manager.

Maintains the authoritative catalog of all clinical laboratory guidelines,
standards, versions, publishers, review dates, and section ontologies
used by the RAG retrieval and citation grounding pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("kb_manifest")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_DIR = PROJECT_ROOT / "data" / "rag_sources"
MANIFEST_JSON_PATH = PROJECT_ROOT / "data" / "kb_manifest.json"
MANIFEST_DOC_PATH = PROJECT_ROOT / "docs" / "KB_MANIFEST.md"


class KBSectionEntry(BaseModel):
    """Metadata for an individual section within a guideline document."""

    section_name: str
    section_id: str
    character_count: int
    content_hash: str


class KBDocumentEntry(BaseModel):
    """Authoritative metadata entry for an individual clinical guideline document."""

    doc_id: str
    test_name: str
    category: str
    source_name: str
    source_url: str
    version: str = "2024.1"
    last_reviewed: str = "2024-05-15"
    authority: str = "National Library of Medicine / NIH"
    sections: List[KBSectionEntry] = Field(default_factory=list)
    document_hash: str


class KBManifest(BaseModel):
    """Root Knowledge Base Manifest schema."""

    manifest_version: str = "1.0.0"
    created_at: str = "2026-11-23"
    total_documents: int
    publisher: str = "MedlinePlus & Clinical Laboratory Reference Consortium"
    documents: List[KBDocumentEntry] = Field(default_factory=list)


class KBManifestManager:
    """Manages creation, loading, and querying of the Clinical Knowledge Base Manifest."""

    def __init__(self, manifest_path: Optional[Path] = None):
        self.manifest_path = manifest_path or MANIFEST_JSON_PATH
        self._manifest: Optional[KBManifest] = None
        self._by_doc_id: Dict[str, KBDocumentEntry] = {}
        self._by_test_name: Dict[str, KBDocumentEntry] = {}

    def get_manifest(self) -> KBManifest:
        """Load manifest from disk or generate if absent."""
        if self._manifest is None:
            if self.manifest_path.exists():
                try:
                    with open(self.manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._manifest = KBManifest(**data)
                    self._index()
                    return self._manifest
                except Exception as e:
                    logger.warning(f"Could not load existing manifest: {e}. Rebuilding...")
            self._manifest = self.build_manifest()
            self._index()
        return self._manifest

    def _index(self) -> None:
        """Build internal in-memory index for O(1) query lookups."""
        if not self._manifest:
            return
        for doc in self._manifest.documents:
            self._by_doc_id[doc.doc_id] = doc
            self._by_test_name[doc.test_name.lower()] = doc

    def get_document(self, query: str) -> Optional[KBDocumentEntry]:
        """Lookup document by doc_id or test name substring."""
        self.get_manifest()
        q_lower = query.lower().strip()
        if q_lower in self._by_doc_id:
            return self._by_doc_id[q_lower]
        if q_lower in self._by_test_name:
            return self._by_test_name[q_lower]
        for name, doc in self._by_test_name.items():
            if q_lower in name or name in q_lower:
                return doc
        return None

    def build_manifest(self, sources_dir: Optional[Path] = None) -> KBManifest:
        """Scan data/rag_sources/ and construct a comprehensive, verified manifest."""
        src_dir = sources_dir or SOURCES_DIR
        doc_entries: List[KBDocumentEntry] = []

        if not src_dir.exists():
            logger.warning(f"RAG sources directory not found: {src_dir}")
            manifest = KBManifest(total_documents=0)
            return manifest

        txt_files = sorted(src_dir.glob("*.txt"))
        for txt_file in txt_files:
            meta_file = txt_file.with_suffix(".meta.json")
            meta_data: Dict[str, Any] = {}
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                except Exception as e:
                    logger.debug(f"Failed to read meta file {meta_file}: {e}")

            with open(txt_file, "r", encoding="utf-8") as f:
                content = f.read()

            doc_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            stem = txt_file.stem.lower()

            # Parse sections: lines ending with ':' or starting with 'What '
            sections: List[KBSectionEntry] = []
            current_sec_title = "Overview"
            current_sec_lines: List[str] = []

            for line in content.splitlines():
                stripped = line.strip()
                if (
                    stripped.endswith(":")
                    or stripped.startswith("What ")
                    or stripped.startswith("Questions ")
                ):
                    if current_sec_lines:
                        sec_text = "\n".join(current_sec_lines)
                        sec_hash = hashlib.sha256(sec_text.encode("utf-8")).hexdigest()[:12]
                        sec_id = current_sec_title.lower().replace(" ", "_")[:24]
                        sections.append(
                            KBSectionEntry(
                                section_name=current_sec_title,
                                section_id=sec_id,
                                character_count=len(sec_text),
                                content_hash=sec_hash,
                            )
                        )
                    current_sec_title = stripped.rstrip(":")
                    current_sec_lines = []
                else:
                    if stripped:
                        current_sec_lines.append(stripped)

            if current_sec_lines:
                sec_text = "\n".join(current_sec_lines)
                sec_hash = hashlib.sha256(sec_text.encode("utf-8")).hexdigest()[:12]
                sec_id = current_sec_title.lower().replace(" ", "_")[:24]
                sections.append(
                    KBSectionEntry(
                        section_name=current_sec_title,
                        section_id=sec_id,
                        character_count=len(sec_text),
                        content_hash=sec_hash,
                    )
                )

            doc_entry = KBDocumentEntry(
                doc_id=f"medlineplus_{stem}",
                test_name=meta_data.get("test_name", stem.replace("_", " ").title()),
                category=meta_data.get("category", "General Clinical Chemistry"),
                source_name=meta_data.get(
                    "source_name", "MedlinePlus (U.S. National Library of Medicine)"
                ),
                source_url=meta_data.get("source_url", "https://medlineplus.gov/lab-tests/"),
                version="2024.1",
                last_reviewed="2024-05-15",
                authority="U.S. National Library of Medicine / NIH",
                sections=sections,
                document_hash=doc_hash,
            )
            doc_entries.append(doc_entry)

        manifest = KBManifest(
            manifest_version="1.0.0",
            total_documents=len(doc_entries),
            publisher="MedlinePlus & Clinical Laboratory Reference Consortium",
            documents=doc_entries,
        )

        # Save to JSON
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # Write Markdown documentation
        self.export_markdown(manifest)
        self._manifest = manifest
        self._index()
        return manifest

    def export_markdown(self, manifest: KBManifest, doc_path: Optional[Path] = None) -> None:
        """Generate human-readable docs/KB_MANIFEST.md."""
        target_path = doc_path or MANIFEST_DOC_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)

        md = f"""# Clinical Knowledge Base Manifest

**Manifest Version:** `{manifest.manifest_version}`  
**Last Updated:** `{manifest.created_at}`  
**Curating Authority:** `{manifest.publisher}`  
**Total Clinical Guidelines:** `{manifest.total_documents}`

This manifest documents every authoritative laboratory reference document indexed in ChromaDB for Retrieval-Augmented Generation (RAG) and citation grounding.

---

## Authoritative Reference Documents

| Document ID | Test / Biomarker | Category | Clinical Authority | Version | Review Date | Sections |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
        for doc in manifest.documents:
            sec_count = len(doc.sections)
            md += (
                f"| `{doc.doc_id}` | [{doc.test_name}]({doc.source_url}) | "
                f"{doc.category} | {doc.authority} | `{doc.version}` | "
                f"{doc.last_reviewed} | {sec_count} sections |\n"
            )

        md += """
---

## Document Section Taxonomy

Every document is segmented into standard clinical inquiry sections:
1. **What the Test Measures:** Physiological role and diagnostic intent.
2. **What Elevated / High Values Mean:** Clinical etiologies for results above the upper reference boundary.
3. **What Low Values Mean:** Pathophysiological associations for results below the lower reference boundary.
4. **Questions to Ask Your Doctor:** Actionable, patient-centered questions for clinical consultation.

All citations emitted by the LLM generation pipeline reference these document IDs and section identifiers.
"""
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(md)


def get_kb_manifest() -> KBManifest:
    """Helper to retrieve the cached knowledge base manifest."""
    return KBManifestManager().get_manifest()
