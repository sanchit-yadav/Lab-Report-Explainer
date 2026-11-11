"""Document indexer populating ChromaDB with curated clinical knowledge."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.api.models.Collection import Collection

from src.config import RAGConfig, get_config
from src.rag.embeddings import EmbeddingManager

logger = logging.getLogger("indexer")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCES_DIR = PROJECT_ROOT / "data" / "rag_sources"


class DocumentIndexer:
    """Ingests medical reference documents, embeds them, and stores in ChromaDB."""

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        sources_dir: Optional[Path] = None,
    ):
        self.config = config or get_config().rag
        self.sources_dir = sources_dir or DEFAULT_SOURCES_DIR
        self.embedder = EmbeddingManager(self.config.embeddings)
        self.chroma_client = chromadb.PersistentClient(
            path=str(PROJECT_ROOT / self.config.vector_store.persist_directory)
        )
        self.collection_name = self.config.vector_store.collection_name

    def get_collection(self) -> Collection:
        """Retrieve or create the ChromaDB collection."""
        return self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Curated clinical laboratory reference guidelines"},
        )

    def load_documents(self) -> List[Dict[str, Any]]:
        """Load text and metadata for all documents in the sources directory."""
        docs: List[Dict[str, Any]] = []
        if not self.sources_dir.exists():
            logger.warning(f"Sources directory does not exist: {self.sources_dir}")
            return docs

        txt_files = sorted(self.sources_dir.glob("*.txt"))
        for txt_file in txt_files:
            meta_file = txt_file.with_suffix(".meta.json")
            with open(txt_file, "r", encoding="utf-8") as f:
                content = f.read().strip()

            meta = {}
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)

            doc_id = txt_file.stem
            docs.append({
                "id": doc_id,
                "content": content,
                "metadata": {
                    "test_name": meta.get("test_name", doc_id),
                    "category": meta.get("category", "General"),
                    "source_name": meta.get("source_name", "Clinical Guideline"),
                    "source_url": meta.get("source_url", ""),
                    "language": meta.get("language", "en"),
                },
            })
        return docs

    def index_all(self, force_reindex: bool = False) -> int:
        """Embed and upsert all curated documents into ChromaDB."""
        collection = self.get_collection()
        existing_count = collection.count()

        if existing_count > 0 and not force_reindex:
            logger.info(f"ChromaDB collection already contains {existing_count} documents. Skipping re-indexing.")
            return existing_count

        docs = self.load_documents()
        if not docs:
            logger.warning("No documents found to index.")
            return 0

        doc_ids = [d["id"] for d in docs]
        texts = [d["content"] for d in docs]
        metadatas = [d["metadata"] for d in docs]

        logger.info(f"Generating embeddings for {len(texts)} documents...")
        embeddings = self.embedder.embed_documents(texts)

        # Upsert into ChromaDB
        collection.upsert(
            ids=doc_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info(f"Successfully indexed {len(doc_ids)} documents into ChromaDB collection '{self.collection_name}'.")
        return len(doc_ids)


if __name__ == "__main__":
    indexer = DocumentIndexer()
    count = indexer.index_all(force_reindex=True)
    print(f"Indexed {count} documents into ChromaDB.")
